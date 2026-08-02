"""Vercel serverless backend for the learn-with-claude web app.

One function serves every /api/* route (see vercel.json rewrites). The route
handlers — shared with the local Copilot server — live in
`learn_with_claude/webapi.py`; this file supplies the Vercel transport
(HTTP handler, cookie auth) and the Anthropic Messages API `call_model`.

State lives in the browser: the client holds the knowledge tree (the same
portable .know.json shape the CLI writes) and drives the learner↔tutor loop
one model call per request, sending the turn history each time. That keeps
every request well under the function time limit and the server stateless.

Env vars:
  APP_PASSWORD       required — the login password
  LEARN_PROVIDER     "anthropic" (default) or "deepseek" — which API answers
  ANTHROPIC_API_KEY  required for the anthropic provider
  DEEPSEEK_API_KEY   required for the deepseek provider
  LEARN_LEARNER_MODEL / LEARN_TUTOR_MODEL   default claude-sonnet-5
  LEARN_EFFORT       default xhigh (anthropic only — DeepSeek has no equivalent)
  LEARN_MAX_TURNS    default 20

The provider is a switch rather than a rewrite: both transports satisfy the
same call_model() contract webapi.model_routes() expects, so every route,
prompt and cost display works either way and flipping back is one env var.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learn_with_claude import deepseek_backend, gemini_images  # noqa: E402
from learn_with_claude.personas import LEARNER_LEVELS, TUTOR_MODES  # noqa: E402
from learn_with_claude.webapi import (  # noqa: E402
    ApiError,
    model_routes,
    split_tutor_parts,  # noqa: F401  (re-export; tests import it from here)
)

PROVIDER = os.environ.get("LEARN_PROVIDER", "anthropic").strip().lower()
USING_DEEPSEEK = PROVIDER == "deepseek"

# The SDK is the package's only third-party dependency and it is imported for
# one provider. On DeepSeek (stdlib urllib) a missing or broken install must
# not take the deployment down with it.
anthropic = None
if not USING_DEEPSEEK:
    import anthropic  # noqa: E402

LEARNER_MODEL = os.environ.get("LEARN_LEARNER_MODEL", "claude-sonnet-5")
TUTOR_MODEL = os.environ.get("LEARN_TUTOR_MODEL", "claude-sonnet-5")
# glossary definitions are two plain sentences — a small fast model is plenty
GLOSSARY_MODEL = os.environ.get("LEARN_GLOSSARY_MODEL", "claude-haiku-4-5-20251001")
# setting a written paper and marking essays against its own mark scheme are
# the two hardest judgement calls the app makes, and the two whose failures are
# least visible to the person they land on — a soft mark reads exactly like a
# good one. So the examiner gets the strongest model by default; set
# LEARN_EXAMINER_MODEL to the tutor's model to bring the cost back down.
EXAMINER_MODEL = os.environ.get("LEARN_EXAMINER_MODEL", "claude-opus-5")
# ⚡ fact me out is bounded by what the model KNOWS, not by how well it
# reasons — and it is one call the reader then treats as reference, so a
# half-remembered number here is repeated rather than caught. Breadth and
# recall accuracy are exactly what the strongest model buys, so it gets one.
FACTS_MODEL = os.environ.get("LEARN_FACTS_MODEL", "claude-opus-5")
# 🔍 double-check reads back every tutor reply before it is shown. Unlike the
# examiner it runs on EVERY turn, so the default is the tutor's own model
# rather than the strongest one — a third opus call per turn would roughly
# treble the bill for a conversation. Set LEARN_REVIEWER_MODEL to claude-opus-5
# if catching the subtle ones matters more than the cost.
REVIEWER_MODEL = os.environ.get("LEARN_REVIEWER_MODEL", TUTOR_MODEL)
EFFORT = os.environ.get("LEARN_EFFORT", "xhigh")
MAX_TURNS = int(os.environ.get("LEARN_MAX_TURNS", "20"))

ROLE_MODELS = {"learner": LEARNER_MODEL, "tutor": TUTOR_MODEL,
               "glossary": GLOSSARY_MODEL, "examiner": EXAMINER_MODEL,
               "facts": FACTS_MODEL, "reviewer": REVIEWER_MODEL}

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

_client = anthropic.Anthropic(timeout=280.0, max_retries=1) if anthropic else None


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
# model transport — the Anthropic Messages API
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
    system: str, messages: list, role: str,
    effort: "str | None" = None, max_tokens: int = 16000,
) -> tuple[str, float]:
    if USING_DEEPSEEK:
        try:
            return deepseek_backend.call_model(system, messages, role,
                                               effort=effort, max_tokens=max_tokens)
        except deepseek_backend.DeepSeekError as exc:
            raise ApiError(str(exc), exc.status) from exc
    model = ROLE_MODELS.get(role, TUTOR_MODEL)
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


def handle_login(body: dict) -> tuple[dict, str]:
    configured = os.environ.get("APP_PASSWORD", "")
    if not configured:
        raise ApiError("APP_PASSWORD is not configured on the server", 500)
    given = str(body.get("password") or "")
    if not hmac.compare_digest(given.encode(), configured.encode()):
        raise ApiError("wrong password", 401)
    return {"ok": True}, make_token()


def handle_config() -> dict:
    # the model names travel to the browser, where they land in the per-node
    # chips and the cost tooltip — so they have to name the model that
    # actually answered, not the one this file defaults to
    return {
        "provider": PROVIDER,
        "learner_model": (deepseek_backend.model_for("learner") if USING_DEEPSEEK
                          else LEARNER_MODEL),
        "tutor_model": (deepseek_backend.model_for("tutor") if USING_DEEPSEEK
                        else TUTOR_MODEL),
        "effort": "" if USING_DEEPSEEK else EFFORT,
        "max_turns": MAX_TURNS,
        "modes": list(TUTOR_MODES),
        "levels": list(LEARNER_LEVELS),
        # 🖼 illustrate needs a Gemini key the deployment may not have — the
        # client hides the button rather than offering an action that can only
        # fail, so this has to travel with the config
        "images": gemini_images.available(),
        "image_model": gemini_images.model_name() if gemini_images.available() else "",
    }


ROUTES = model_routes(call_model)


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
