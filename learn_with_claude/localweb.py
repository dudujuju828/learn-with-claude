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
  * custom tutors live next to them in tutors.json.

Binds 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import copilot_backend
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

ROUTES = model_routes(copilot_backend.call_model)


def handle_config() -> dict:
    models = {r: m or "auto" for r, m in copilot_backend.ROLE_MODELS.items()}
    return {
        "learner_model": models["learner"],
        "tutor_model": models["tutor"],
        "effort": copilot_backend.EFFORT or "default",
        "max_turns": MAX_TURNS,
        "modes": list(TUTOR_MODES),
        "levels": list(LEARNER_LEVELS),
        "local": True,
        "provider": "copilot",
    }


# --------------------------------------------------------------------------- #
# trees on disk — the same files the CLI shell reads and writes
# --------------------------------------------------------------------------- #
class TreeStore:
    """id -> .know.json file in the knowledge dir. Filenames follow the CLI's
    topic-slug convention; the documents are stored verbatim (the web tree
    carries fields like quiz/saved_at this package's KnowledgeTree doesn't
    model, and round-tripping through it would drop them)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()

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
            trees = []
            for tid, (path, _doc) in self._scan().items():
                st = path.stat()
                trees.append({
                    "id": tid,
                    "size": st.st_size,
                    "uploadedAt": _iso(st.st_mtime),
                })
            return trees

    def get(self, tid: str) -> "dict | None":
        with self.lock:
            hit = self._scan().get(tid)
            return hit[1] if hit else None

    def put(self, tree: dict) -> None:
        tid = str(tree.get("id") or "")
        if tree.get("format") != FORMAT or not _TREE_ID.match(tid):
            raise ApiError("body must be {tree} in knowledge-tree format")
        with self.lock:
            known = self._scan()
            if tid in known:
                path = known[tid][0]
            else:
                stem = slug(str(tree.get("root_topic") or "") or tid) or tid
                path = self.root / f"{stem}.know.json"
                n = 2
                while path.exists():  # same topic, different tree
                    path = self.root / f"{stem}-{n}.know.json"
                    n += 1
            self.root.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(tree, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def delete(self, tid: str) -> None:
        with self.lock:
            hit = self._scan().get(tid)
            if hit:
                hit[0].unlink(missing_ok=True)


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
            for t in tutors
        )


# --------------------------------------------------------------------------- #
# http
# --------------------------------------------------------------------------- #
def make_handler(trees: TreeStore, tutors: TutorStore):
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
                    trees.put(body.get("tree") if isinstance(body.get("tree"), dict) else {})
                    self._send_json(200, {"ok": True})
                elif path == "/api/tutors":
                    tutors.put(body.get("doc"))
                    self._send_json(200, {"ok": True})
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
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(trees, tutors))
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
