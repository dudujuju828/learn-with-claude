"""Vercel serverless backend for the learn-with-claude web app.

One function serves every /api/* route (see vercel.json rewrites). It reuses
the exact prompts and loop semantics from the CLI — `personas.py`,
`knowledge.py`, `render.py`, and the learner-turn parser from `simulator.py`
are imported untouched — but talks to the Anthropic Messages API directly
instead of shelling out to the `claude` CLI (which can't run on Vercel).

State lives in the browser: the client holds the knowledge tree (the same
portable .know.json shape the CLI writes) and drives the learner↔tutor loop
one model call per request, sending the turn history each time. That keeps
every request well under the function time limit and the server stateless.

Env vars:
  APP_PASSWORD       required — the login password
  ANTHROPIC_API_KEY  required — picked up by the anthropic SDK
  LEARN_LEARNER_MODEL / LEARN_TUTOR_MODEL   default claude-sonnet-5
  LEARN_EFFORT       default xhigh
  LEARN_MAX_TURNS    default 20
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learn_with_claude.knowledge import KnowledgeTree, conversation_digest  # noqa: E402
from learn_with_claude.personas import (  # noqa: E402
    GLOSSARY_SYSTEM,
    LEARNER_LEVELS,
    NEXT_CONCEPT_SYSTEM,
    TUTOR_MODES,
    branch_learner_message,
    branch_tutor_context,
    define_message,
    feedback_message,
    first_learner_message,
    followup_learner_message,
    followup_tutor_context,
    learner_system,
    next_concept_message,
    tutor_system,
)
from learn_with_claude.render import space_sentences  # noqa: E402
from learn_with_claude.simulator import clean_term, extract_turn, first_json_object  # noqa: E402

import anthropic  # noqa: E402

LEARNER_MODEL = os.environ.get("LEARN_LEARNER_MODEL", "claude-sonnet-5")
TUTOR_MODEL = os.environ.get("LEARN_TUTOR_MODEL", "claude-sonnet-5")
# glossary definitions are two plain sentences — a small fast model is plenty
GLOSSARY_MODEL = os.environ.get("LEARN_GLOSSARY_MODEL", "claude-haiku-4-5-20251001")
EFFORT = os.environ.get("LEARN_EFFORT", "xhigh")
MAX_TURNS = int(os.environ.get("LEARN_MAX_TURNS", "20"))

COOKIE_NAME = "lwc_auth"
TOKEN_DAYS = 30

# USD per million tokens (input, output), matched by model-id prefix. Cache
# writes bill at 1.25x input, cache reads at 0.1x. Close enough for the same
# per-tree cost feel the CLI gives.
PRICES = [
    ("claude-opus", (5.0, 25.0)),
    ("claude-sonnet", (3.0, 15.0)),
    ("claude-haiku", (1.0, 5.0)),
]

_client = anthropic.Anthropic(timeout=280.0, max_retries=1)


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# auth — a signed expiry timestamp in an HttpOnly cookie
# --------------------------------------------------------------------------- #
def _secret() -> bytes:
    pw = os.environ.get("APP_PASSWORD", "")
    return hashlib.sha256(b"learn-with-claude-web:" + pw.encode("utf-8")).digest()


def make_token() -> str:
    exp = str(int(time.time()) + TOKEN_DAYS * 86400)
    sig = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def token_valid(token: str) -> bool:
    exp, _, sig = token.partition(".")
    if not exp or not sig:
        return False
    want = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, want):
        return False
    try:
        return int(exp) > time.time()
    except ValueError:
        return False


def cookie_token(cookie_header: str) -> str:
    for part in (cookie_header or "").split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME:
            return value
    return ""


# --------------------------------------------------------------------------- #
# model calls
# --------------------------------------------------------------------------- #
def usage_cost(model: str, usage) -> float:
    pin, pout = 3.0, 15.0
    for prefix, (i, o) in PRICES:
        if model.startswith(prefix):
            pin, pout = i, o
            break
    cache_w = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_r = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (
        usage.input_tokens * pin
        + cache_w * pin * 1.25
        + cache_r * pin * 0.10
        + usage.output_tokens * pout
    ) / 1_000_000


def call_model(
    system: str, messages: list, model: str,
    effort: "str | None" = None, max_tokens: int = 16000,
) -> tuple[str, float]:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ApiError(
            "ANTHROPIC_API_KEY is not set on the server — add it in the Vercel "
            "project settings (or `vercel env add ANTHROPIC_API_KEY production`) "
            "and redeploy",
            500,
        )
    if effort is None:
        effort = EFFORT
    extra = {} if effort == "none" else {"output_config": {"effort": effort}}
    try:
        resp = _client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            **extra,
        )
    except anthropic.AuthenticationError:
        raise ApiError("ANTHROPIC_API_KEY is missing or invalid on the server", 500)
    except anthropic.RateLimitError:
        raise ApiError("rate limited by the Anthropic API — wait a moment and retry", 429)
    except anthropic.APIStatusError as exc:
        raise ApiError(f"Anthropic API error {exc.status_code}: {exc.message}", 502)
    except anthropic.APIConnectionError:
        raise ApiError("could not reach the Anthropic API", 502)

    if resp.stop_reason == "refusal":
        raise ApiError("the model declined this request", 502)
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    return text, usage_cost(model, resp.usage)


# --------------------------------------------------------------------------- #
# prompt reconstruction — mirrors run_conversation() in simulator.py
# --------------------------------------------------------------------------- #
def learner_opening(body: dict) -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        return branch_learner_message(
            body["topic"], body.get("breadcrumb", ""), body.get("digest", ""),
            body.get("branch_q", ""), body.get("branch_a", ""), body.get("focus", ""),
        )
    if kind == "followup":
        return followup_learner_message(
            body["topic"], body.get("recap", ""),
            body.get("concept", ""), body.get("opening_question", ""),
        )
    return first_learner_message(body["topic"])


def tutor_extra_context(body: dict) -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        return branch_tutor_context(body.get("digest", ""), body.get("branch_a", ""))
    if kind == "followup":
        return followup_tutor_context(body.get("recap", ""), body.get("concept", ""))
    return ""


def turn_json(turn: dict) -> str:
    """The learner's turn re-serialised as the JSON object it originally
    emitted — used as the assistant side when rebuilding its conversation."""
    return json.dumps(
        {
            "thinking": turn.get("thinking") or "",
            "new_term": turn.get("new_term") or None,
            "action": turn.get("action") or "",
            "confidence": turn.get("confidence"),
            "done": bool(turn.get("done")),
        },
        ensure_ascii=False,
    )


def handle_learner(body: dict) -> dict:
    level = body.get("level")
    if level not in LEARNER_LEVELS:
        level = "student"
    messages = [{"role": "user", "content": learner_opening(body)}]
    for t in body.get("turns", []):
        messages.append({"role": "assistant", "content": turn_json(t)})
        messages.append({"role": "user", "content": feedback_message(t.get("tutor", ""))})
    text, cost = call_model(learner_system(level), messages, LEARNER_MODEL)
    data = extract_turn(text)
    return {
        "thinking": (data.get("thinking") or "").strip(),
        "new_term": clean_term(data.get("new_term")),
        "action": (data.get("action") or "").strip(),
        "confidence": data.get("confidence"),
        "done": bool(data.get("done")),
        "cost": cost,
    }


# A part tag: a short bracketed label alone at the start of a line, e.g.
# "[why]" or "[so where does the copy live?]". Purely numeric labels (citation
# style, "[1]") don't count, and code fences are skipped while scanning.
_PART_TAG = re.compile(r"^\s*\[([^\[\]\n]{2,60})\]\s*(.*)$")


def split_tutor_parts(text: str) -> list:
    """Split a tutor reply on its [label] markup lines into
    [{"label": str, "text": str}, ...]. The opening (untagged) answer comes
    back as a part with label "". Returns [] when there is no markup at all."""
    parts = [{"label": "", "lines": []}]
    in_code = False
    for line in (text or "").split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            parts[-1]["lines"].append(line)
            continue
        m = None if in_code else _PART_TAG.match(line)
        label = (m.group(1).strip() if m else "")
        if m and label and not label.isdigit():
            parts.append({"label": label, "lines": [m.group(2)] if m.group(2).strip() else []})
        else:
            parts[-1]["lines"].append(line)
    out = []
    for p in parts:
        body = "\n".join(p["lines"]).strip()
        if body or p["label"]:
            out.append({"label": p["label"], "text": body})
    if len(out) < 2:
        return []
    return out


def handle_tutor(body: dict) -> dict:
    action = (body.get("action") or "").strip()
    if not action:
        raise ApiError("missing 'action'")
    mode = body.get("mode")
    if mode not in TUTOR_MODES:
        mode = "balanced"
    custom = body.get("custom_style")
    if not isinstance(custom, str):
        custom = None
    elif len(custom) > 4000:
        custom = custom[:4000]
    system = tutor_system(diagrams=False, mode=mode, custom_style=custom, segments=True)
    extra = tutor_extra_context(body)
    if extra:
        system += f"\n\n{extra}"
    messages = []
    for t in body.get("turns", []):
        if t.get("action") and t.get("tutor"):
            messages.append({"role": "user", "content": t["action"]})
            messages.append({"role": "assistant", "content": t["tutor"]})
    messages.append({"role": "user", "content": action})
    text, cost = call_model(system, messages, TUTOR_MODEL)
    parts = split_tutor_parts(text)
    if not parts:
        return {"tutor": space_sentences(text), "cost": cost}
    # the stored/plain answer is the parts joined without their tags, so the
    # learner sim, digests, search, and exports all keep seeing clean text
    for p in parts:
        p["text"] = space_sentences(p["text"])
    clean = "\n\n".join(p["text"] for p in parts if p["text"])
    return {"tutor": clean, "parts": parts, "cost": cost}


def handle_next_concept(body: dict) -> dict:
    message = next_concept_message(
        body.get("root_topic", ""), body.get("covered", []), body.get("recap", "")
    )
    text, cost = call_model(
        NEXT_CONCEPT_SYSTEM, [{"role": "user", "content": message}], TUTOR_MODEL
    )
    pick = first_json_object(text)
    if not isinstance(pick, dict) or not str(pick.get("concept") or "").strip():
        pick = None
    return {"pick": pick, "cost": cost}


def handle_define(body: dict) -> dict:
    """One glossary definition, on the cheap model. Context is the exchange
    where the learner hit the term, so the definition matches its use there."""
    term = (body.get("term") or "").strip()
    if not term:
        raise ApiError("missing 'term'")
    message = define_message(
        term[:120],
        (body.get("topic") or "").strip()[:200],
        (body.get("context") or "").strip()[:4000],
    )
    text, cost = call_model(
        GLOSSARY_SYSTEM, [{"role": "user", "content": message}],
        GLOSSARY_MODEL, effort="none", max_tokens=300,
    )
    data = first_json_object(text)
    definition = ""
    if isinstance(data, dict):
        definition = str(data.get("definition") or "").strip()
    if not definition:
        # a small model may answer in prose despite the contract — take it
        definition = text.strip().strip('"')
    return {"definition": definition[:600], "cost": cost}


def handle_export_md(body: dict) -> dict:
    tree = body.get("tree")
    if not isinstance(tree, dict):
        raise ApiError("missing 'tree'")
    kb = KnowledgeTree.from_dict(tree)
    return {"markdown": kb.to_markdown(), "filename": kb.default_filename().replace(".know.json", ".md")}


def handle_export_html(body: dict) -> dict:
    tree = body.get("tree")
    if not isinstance(tree, dict):
        raise ApiError("missing 'tree'")
    from learn_with_claude.export_html import tree_to_html

    kb = KnowledgeTree.from_dict(tree)
    return {"html": tree_to_html(kb), "filename": kb.default_filename().replace(".know.json", ".html")}


def handle_digest(body: dict) -> dict:
    """Server-side conversation_digest so the recap text matches the CLI."""
    return {"digest": conversation_digest(body.get("turns", []), body.get("upto"))}


def handle_login(body: dict) -> tuple[dict, str]:
    configured = os.environ.get("APP_PASSWORD", "")
    if not configured:
        raise ApiError("APP_PASSWORD is not configured on the server", 500)
    given = str(body.get("password") or "")
    if not hmac.compare_digest(given.encode(), configured.encode()):
        raise ApiError("wrong password", 401)
    return {"ok": True}, make_token()


def handle_config() -> dict:
    return {
        "learner_model": LEARNER_MODEL,
        "tutor_model": TUTOR_MODEL,
        "effort": EFFORT,
        "max_turns": MAX_TURNS,
        "modes": list(TUTOR_MODES),
        "levels": list(LEARNER_LEVELS),
    }


ROUTES = {
    "learner": handle_learner,
    "tutor": handle_tutor,
    "next_concept": handle_next_concept,
    "define": handle_define,
    "export_md": handle_export_md,
    "export_html": handle_export_html,
    "digest": handle_digest,
}


class handler(BaseHTTPRequestHandler):
    def _send(
        self, status: int, payload: dict,
        set_cookie: str | None = None, cookie_max_age: int = TOKEN_DAYS * 86400,
    ) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        if set_cookie is not None:
            self.send_header(
                "Set-Cookie",
                f"{COOKIE_NAME}={set_cookie}; Max-Age={cookie_max_age}; "
                "Path=/; HttpOnly; Secure; SameSite=Lax",
            )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self) -> str:
        path = self.path.split("?")[0].rstrip("/")
        return path.rsplit("/", 1)[-1]

    def _authed(self) -> bool:
        return token_valid(cookie_token(self.headers.get("Cookie", "")))

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ApiError("invalid JSON body")

    def do_GET(self) -> None:  # noqa: N802
        route = self._route()
        if route == "me":
            if self._authed():
                self._send(200, handle_config())
            else:
                self._send(401, {"error": "not logged in"})
        else:
            self._send(404, {"error": f"no such route: {route}"})

    def do_POST(self) -> None:  # noqa: N802
        route = self._route()
        try:
            body = self._body()
            if route == "login":
                payload, token = handle_login(body)
                self._send(200, payload, set_cookie=token)
                return
            if route == "logout":
                self._send(200, {"ok": True}, set_cookie="", cookie_max_age=0)
                return
            if not self._authed():
                self._send(401, {"error": "not logged in"})
                return
            fn = ROUTES.get(route)
            if fn is None:
                self._send(404, {"error": f"no such route: {route}"})
                return
            self._send(200, fn(body))
        except ApiError as exc:
            self._send(exc.status, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - last-resort surface
            self._send(500, {"error": f"server error: {exc}"})

    def log_message(self, *args) -> None:  # keep function logs quiet
        pass
