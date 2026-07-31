"""The web app as a private localhost server, backed by the Copilot CLI.

    python -m learn_with_claude.localweb        # or:  learn --web

Serves public/index.html and the same /api routes as the Vercel deployment,
with three differences:

  * model calls go through the local `copilot` login (copilot_backend.py) —
    no API key, no APP_PASSWORD, no login screen, nothing leaves this machine
    except Copilot's own traffic;
  * trees persist as .know.json files in the CLI's knowledge directory
    ($LEARN_DIR or ~/.learn-with-claude/knowledge), so the shell and the web
    app grow the same collection;
  * custom tutors live next to them in tutors.json, the profile registry
    (the named interest areas trees file under, and which one is active) in
    profiles.json, the model/effort/project-directory/MCP-server settings
    (local_settings.py) in local_settings.json, and the global question bank
    (questions banked from anywhere, investigated as a fresh root topic) in
    global_questions.json.

Binds 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import copilot_backend, copilot_sessions, local_settings
from .knowledge import FORMAT, slug
from .personas import LEARNER_LEVELS, TUTOR_MODES
from .webapi import ApiError, model_routes

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"
DEFAULT_DIR = os.environ.get("LEARN_DIR") or str(Path.home() / ".learn-with-claude" / "knowledge")
MAX_TURNS = int(os.environ.get("LEARN_MAX_TURNS", "20"))

STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

_TREE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_TUTOR_ID = re.compile(r"^[a-z0-9-]{1,32}$")
_GQ_ID = re.compile(r"^[a-f0-9]{8,32}$")
_PROFILE_BAD = re.compile(r"""['"\\<>&]""")

ROUTES = model_routes(copilot_backend.call_model,
                      tutor_grounding=copilot_backend.grounding_text,
                      learner_grounding=copilot_backend.learner_brief)


def handle_config() -> dict:
    return {
        "learner_model": copilot_backend.effective_model("learner") or "auto",
        "tutor_model": copilot_backend.effective_model("tutor") or "auto",
        "effort": copilot_backend.effective_effort() or "default",
        "max_turns": MAX_TURNS,
        "modes": list(TUTOR_MODES),
        "levels": list(LEARNER_LEVELS),
        "local": True,
        "provider": "copilot",
    }


# --------------------------------------------------------------------------- #
# local settings — models, effort, project dir, MCP servers (Confluence etc.)
# --------------------------------------------------------------------------- #
class LocalSettingsEndpoint:
    """Thin HTTP-shaped wrapper around a LocalSettingsStore: GET returns the
    saved settings plus which MCP servers this Copilot CLI already knows
    about (so the panel can render a checklist, not a form for redefining
    them); POST validates strictly, persists, and immediately reconfigures
    copilot_backend so the next model call already sees the change — no
    server restart. `register()` is the one-click Confluence button: it
    shells out to `copilot mcp add` on the operator's behalf, the same as if
    they'd typed the command themselves."""

    PRESETS = {"confluence": local_settings.CONFLUENCE_PRESET}

    def __init__(self, store: local_settings.LocalSettingsStore) -> None:
        self.store = store

    def _payload(self, doc: dict) -> dict:
        # session_info is how the panel says "yes, that's the one" (or reports
        # a session that has since been deleted); available_sessions is the
        # picker, so nobody has to go hunting for the id by hand
        chosen = doc.get("tutor_session") or ""
        return {
            **doc,
            "presets": self.PRESETS,
            "available_mcp_servers": copilot_backend.list_global_mcp_servers(),
            "available_sessions": copilot_sessions.recent(),
            "session_info": copilot_sessions.describe(chosen) if chosen else None,
        }

    def get(self) -> dict:
        return self._payload(self.store.load())

    def put(self, body: dict) -> dict:
        try:
            clean = self.store.save(body if isinstance(body, dict) else {})
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        copilot_backend.configure(clean)
        return self._payload(clean)

    def register(self, preset_name: str) -> dict:
        preset = self.PRESETS.get(preset_name)
        if not preset:
            raise ApiError(f'no such preset: "{preset_name}"')
        copilot_backend.add_global_mcp_server(
            preset["name"], transport=preset["transport"], url=preset["url"],
        )
        return self._payload(self.store.load())


# --------------------------------------------------------------------------- #
# trees on disk — the same files the CLI shell reads and writes
# --------------------------------------------------------------------------- #
_LEGACY = object()  # "no base_rev in the request" sentinel


class TreeStore:
    """id -> .know.json file in the knowledge dir. Filenames follow the CLI's
    topic-slug convention; the documents are stored verbatim (the web tree
    carries fields like quiz/saved_at this package's KnowledgeTree doesn't
    model, and round-tripping through it would drop them).

    Speaks the same rev protocol as the Vercel backend (api/trees.js): each
    doc carries a stamped integer ``rev``; a put says which rev it was based
    on and conflicts (409) when that is stale; deletions leave a tombstone in
    .tombstones.json. A file the CLI rewrote loses its stamp — its rev is
    then derived from the file mtime, which is larger than any stamped rev,
    so the web client pulls the CLI's changes and merges instead of skipping
    them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()

    @staticmethod
    def _rev_of(doc: dict, path: Path) -> int:
        rev = doc.get("rev")
        if isinstance(rev, int) and rev > 0:
            return rev
        try:
            return int(path.stat().st_mtime)
        except OSError:
            return 1

    def _tombstones(self) -> dict:
        try:
            data = json.loads((self.root / ".tombstones.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_tombstones(self, stones: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".tombstones.json").write_text(
            json.dumps(stones, indent=2), encoding="utf-8"
        )

    def _scan(self) -> dict:
        """id -> (path, doc). Unreadable or foreign files are skipped."""
        out = {}
        for path in sorted(self.root.glob("*.know.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(doc, dict) and doc.get("format") == FORMAT and doc.get("id"):
                out[str(doc["id"])] = (path, doc)
        return out

    def list(self) -> list:
        with self.lock:
            known = self._scan()
            trees = []
            for tid, (path, doc) in known.items():
                st = path.stat()
                trees.append({
                    "id": tid,
                    "rev": self._rev_of(doc, path),
                    "deleted": False,
                    "size": st.st_size,
                    "updated_at": _iso(st.st_mtime),
                    "uploadedAt": _iso(st.st_mtime),
                })
            for tid, stone in self._tombstones().items():
                if tid in known:
                    continue  # the file reappeared (restored backup): it wins
                trees.append({
                    "id": tid, "rev": int(stone.get("rev") or 1), "deleted": True,
                    "size": 0, "updated_at": stone.get("at") or "",
                    "uploadedAt": stone.get("at") or "",
                })
            return trees

    def get(self, tid: str) -> "dict | None":
        with self.lock:
            hit = self._scan().get(tid)
            if not hit:
                return None
            path, doc = hit
            doc["rev"] = self._rev_of(doc, path)
            return doc

    def put(self, tree: dict, base_rev=_LEGACY) -> dict:
        """Returns {"ok": True, "rev": n} or {"conflict": <409 body>}."""
        tid = str(tree.get("id") or "")
        if tree.get("format") != FORMAT or not _TREE_ID.match(tid):
            raise ApiError("body must be {tree} in knowledge-tree format")
        with self.lock:
            known = self._scan()
            stones = self._tombstones()
            hit = known.get(tid)
            cur_rev = self._rev_of(hit[1], hit[0]) if hit else 0

            if base_rev is _LEGACY:
                pass  # legacy client: last write wins, as before the protocol
            elif hit:
                try:
                    base = int(base_rev or 0)
                except (TypeError, ValueError):
                    base = 0
                if base != cur_rev:
                    stale = dict(hit[1])
                    stale["rev"] = cur_rev
                    return {"conflict": {
                        "error": "conflict: newer revision on server",
                        "rev": cur_rev, "tree": stale,
                    }}
            elif tid in stones:
                try:
                    base = int(base_rev or 0)
                except (TypeError, ValueError):
                    base = 0
                if base > 0:  # an edit of something deleted elsewhere loses
                    return {"conflict": {
                        "error": "conflict: deleted elsewhere",
                        "rev": int(stones[tid].get("rev") or 1), "deleted": True,
                    }}
                cur_rev = int(stones[tid].get("rev") or 1)  # base 0 resurrects

            if hit:
                path = hit[0]
            else:
                stem = slug(str(tree.get("root_topic") or "") or tid) or tid
                path = self.root / f"{stem}.know.json"
                n = 2
                while path.exists():  # same topic, different tree
                    path = self.root / f"{stem}-{n}.know.json"
                    n += 1
            new_rev = cur_rev + 1
            tree = dict(tree)
            tree["rev"] = new_rev
            self.root.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if tid in stones:
                del stones[tid]
                self._write_tombstones(stones)
            return {"ok": True, "rev": new_rev}

    def delete(self, tid: str) -> None:
        with self.lock:
            hit = self._scan().get(tid)
            cur_rev = self._rev_of(hit[1], hit[0]) if hit else 0
            if hit:
                hit[0].unlink(missing_ok=True)
            stones = self._tombstones()
            stones[tid] = {"rev": cur_rev + 1, "at": _iso(time.time())}
            self._write_tombstones(stones)


def _iso(ts: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


# --------------------------------------------------------------------------- #
# custom tutors — one small JSON doc beside the knowledge dir
# --------------------------------------------------------------------------- #
class TutorStore:
    MAX_TUTORS, MAX_NAME, MAX_STYLE = 20, 40, 4000

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def get(self) -> "dict | None":
        with self.lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def put(self, doc) -> None:
        if not self._valid(doc):
            raise ApiError("invalid tutors document")
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    @classmethod
    def _valid(cls, doc) -> bool:
        if not isinstance(doc, dict) or not isinstance(doc.get("tutors"), list):
            return False
        tutors = doc["tutors"]
        if len(tutors) > cls.MAX_TUTORS:
            return False
        return all(
            isinstance(t, dict)
            and _TUTOR_ID.match(str(t.get("id") or ""))
            and isinstance(t.get("name"), str) and t["name"].strip()
            and len(t["name"]) <= cls.MAX_NAME
            and isinstance(t.get("style"), str) and t["style"].strip()
            and len(t["style"]) <= cls.MAX_STYLE
            and cls._scope_ok(t.get("profile"))
            for t in tutors
        )

    @staticmethod
    def _scope_ok(p) -> bool:
        # a tutor may be filed under a profile, offering it only in that
        # interest (see ProfileStore); no filing means "offered everywhere"
        if p is None or p == "":
            return True
        return isinstance(p, str) and len(p) <= 40 and not _PROFILE_BAD.search(p)


# --------------------------------------------------------------------------- #
# global question bank — questions banked from anywhere, not tied to a tree;
# investigated fresh (a new root investigation), unlike tree.questions
# (the per-tree bank, answered as a turn in the node you were reading).
# Same "one small synced JSON doc" shape as TutorStore/tutors.json.
# --------------------------------------------------------------------------- #
class GlobalQuestionStore:
    MAX_QUESTIONS, MAX_TEXT = 300, 500

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def get(self) -> "dict | None":
        with self.lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def put(self, doc) -> None:
        if not self._valid(doc):
            raise ApiError("invalid global questions document")
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    @classmethod
    def _valid(cls, doc) -> bool:
        if not isinstance(doc, dict) or not isinstance(doc.get("questions"), list):
            return False
        qs = doc["questions"]
        if len(qs) > cls.MAX_QUESTIONS:
            return False
        return all(
            isinstance(q, dict)
            and _GQ_ID.match(str(q.get("id") or ""))
            and isinstance(q.get("text"), str) and q["text"].strip()
            and len(q["text"]) <= cls.MAX_TEXT
            for q in qs
        )


# --------------------------------------------------------------------------- #
# profiles — the named interest areas trees file under. The filing itself
# lives on each tree (and so travels in .know.json to the CLI and back); this
# is the REGISTRY, which is what lets a profile exist before its first
# conversation and survive its last tree moving away. `active` rides along so
# the profile you are in is the same in the browser on every visit rather
# than a per-browser guess. Same "one small JSON doc" shape as TutorStore.
# --------------------------------------------------------------------------- #
class ProfileStore:
    MAX_PROFILES, MAX_NAME = 60, 40

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()

    def get(self) -> "dict | None":
        with self.lock:
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return None

    def put(self, doc) -> None:
        if not self._valid(doc):
            raise ApiError("invalid profiles document")
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    @classmethod
    def _name_ok(cls, name) -> bool:
        # mirrors cleanProfileName() in public/index.html: names reach the
        # client inside inline handlers, so quote-ish characters stay out
        return (isinstance(name, str) and name.strip()
                and len(name) <= cls.MAX_NAME
                and not _PROFILE_BAD.search(name))

    @classmethod
    def _valid(cls, doc) -> bool:
        if not isinstance(doc, dict) or not isinstance(doc.get("profiles"), list):
            return False
        if len(doc["profiles"]) > cls.MAX_PROFILES:
            return False
        active = doc.get("active")
        if active not in (None, "") and not cls._name_ok(active):
            return False
        return all(
            isinstance(p, dict) and cls._name_ok(p.get("name"))
            and (p.get("settings") is None or isinstance(p.get("settings"), dict))
            for p in doc["profiles"]
        )


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
def make_handler(trees: TreeStore, tutors: TutorStore, settings: LocalSettingsEndpoint,
                 global_questions: GlobalQuestionStore, profiles: ProfileStore):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        # -- plumbing ----------------------------------------------------- #
        def _send_json(self, status: int, payload) -> None:
            data = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ApiError("invalid JSON body")

        def _split(self) -> tuple[str, dict]:
            path, _, query = self.path.partition("?")
            params = {}
            for part in query.split("&"):
                k, _, v = part.partition("=")
                if k:
                    from urllib.parse import unquote_plus

                    params[k] = unquote_plus(v)
            return path.rstrip("/") or "/", params

        # -- statics ------------------------------------------------------ #
        def _send_static(self, path: str) -> None:
            name = "index.html" if path == "/" else path.lstrip("/")
            file = (PUBLIC_DIR / name).resolve()
            ctype = STATIC_TYPES.get(file.suffix)
            if PUBLIC_DIR not in file.parents or not ctype or not file.is_file():
                self._send_json(404, {"error": "not found"})
                return
            data = file.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        # -- routes ------------------------------------------------------- #
        def do_GET(self) -> None:  # noqa: N802
            path, params = self._split()
            try:
                if path == "/api/me":
                    self._send_json(200, handle_config())
                elif path == "/api/trees":
                    tid = params.get("id", "")
                    if not tid:
                        self._send_json(200, {"trees": trees.list()})
                    elif not _TREE_ID.match(tid):
                        self._send_json(400, {"error": "bad id"})
                    else:
                        doc = trees.get(tid)
                        if doc is None:
                            self._send_json(404, {"error": "no such tree"})
                        else:
                            self._send_json(200, {"tree": doc})
                elif path == "/api/tutors":
                    self._send_json(200, {"doc": tutors.get()})
                elif path == "/api/global_questions":
                    self._send_json(200, {"doc": global_questions.get()})
                elif path == "/api/profiles":
                    self._send_json(200, {"doc": profiles.get()})
                elif path == "/api/local_settings":
                    self._send_json(200, settings.get())
                elif path.startswith("/api/"):
                    self._send_json(404, {"error": "no such route"})
                else:
                    self._send_static(path)
            except ApiError as exc:
                self._send_json(exc.status, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - last-resort surface
                self._send_json(500, {"error": f"server error: {exc}"})

        def do_POST(self) -> None:  # noqa: N802
            path, params = self._split()
            try:
                body = self._body()
                if path == "/api/trees":
                    result = trees.put(
                        body.get("tree") if isinstance(body.get("tree"), dict) else {},
                        body.get("base_rev", _LEGACY) if isinstance(body, dict) else _LEGACY,
                    )
                    if "conflict" in result:
                        self._send_json(409, result["conflict"])
                    else:
                        self._send_json(200, result)
                elif path == "/api/tutors":
                    tutors.put(body.get("doc"))
                    self._send_json(200, {"ok": True})
                elif path == "/api/global_questions":
                    global_questions.put(body.get("doc"))
                    self._send_json(200, {"ok": True})
                elif path == "/api/profiles":
                    profiles.put(body.get("doc"))
                    self._send_json(200, {"ok": True})
                elif path == "/api/local_settings":
                    self._send_json(200, settings.put(body))
                elif path == "/api/mcp_register":
                    self._send_json(200, settings.register(str(body.get("preset") or "")))
                elif path in ("/api/login", "/api/logout"):
                    self._send_json(200, {"ok": True})  # no auth on localhost
                elif path.startswith("/api/"):
                    fn = ROUTES.get(path[len("/api/"):])
                    if fn is None:
                        self._send_json(404, {"error": "no such route"})
                    else:
                        self._send_json(200, fn(body))
                else:
                    self._send_json(404, {"error": "not found"})
            except ApiError as exc:
                self._send_json(exc.status, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - last-resort surface
                self._send_json(500, {"error": f"server error: {exc}"})

        def do_PUT(self) -> None:  # noqa: N802
            self.do_POST()

        def do_DELETE(self) -> None:  # noqa: N802
            path, params = self._split()
            try:
                if path == "/api/trees" and _TREE_ID.match(params.get("id", "")):
                    trees.delete(params["id"])
                    self._send_json(200, {"ok": True})
                else:
                    self._send_json(400, {"error": "bad id"})
            except Exception as exc:  # pragma: no cover
                self._send_json(500, {"error": f"server error: {exc}"})

        def log_message(self, fmt, *args) -> None:
            # statics are noise; model/tree traffic is worth seeing
            if "/api/" in (self.path or ""):
                print(f"  {self.command} {self.path.split('?')[0]}"
                      f" -> {args[1] if len(args) > 1 else ''}")

    return Handler


def serve(port: int = 8577, knowledge_dir: "str | None" = None,
          open_browser: bool = True) -> int:
    root = Path(knowledge_dir or DEFAULT_DIR)
    try:
        version = copilot_backend.verify_copilot()
    except RuntimeError as exc:
        print(f"error: {exc}")
        return 1

    trees = TreeStore(root)
    tutors = TutorStore(root.parent / "tutors.json")
    global_questions = GlobalQuestionStore(root.parent / "global_questions.json")
    profiles = ProfileStore(root.parent / "profiles.json")
    settings_store = local_settings.LocalSettingsStore(root.parent / "local_settings.json")
    copilot_backend.configure(settings_store.load())
    settings = LocalSettingsEndpoint(settings_store)
    httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                make_handler(trees, tutors, settings, global_questions,
                                             profiles))
    url = f"http://localhost:{port}/"
    print(f"learn-with-claude local web · {version}")
    print(f"  trees: {root}")
    print(f"  open:  {url}   (Ctrl+C stops the server)")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()
    return 0


def main(argv: "list[str] | None" = None) -> int:
    p = argparse.ArgumentParser(
        prog="learn --web",
        description="Serve the learn-with-claude web app locally, backed by "
        "your GitHub Copilot login instead of an API key.",
    )
    p.add_argument("--port", type=int, default=8577, help="Port on 127.0.0.1 (default: 8577).")
    p.add_argument("-d", "--dir", default=None,
                   help=f"Knowledge directory (default: $LEARN_DIR or {DEFAULT_DIR}).")
    p.add_argument("--no-open", action="store_true", help="Don't open the browser.")
    args = p.parse_args(argv)
    return serve(port=args.port, knowledge_dir=args.dir, open_browser=not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
