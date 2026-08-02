"""DeepSeek as the model transport — an alternative to the Anthropic API.

Stdlib only (urllib), like gemini_images.py and for the same reason: the
package stays dependency-free, so the Vercel function and anything else that
runs Python can both use this without a pip install. Nothing here knows about
trees, routes, or personas — it exposes one `call_model()` with exactly the
signature webapi.model_routes() expects:

    call_model(system, messages, role, effort=None, max_tokens=16000)
        -> (text, cost_in_usd)

DeepSeek speaks the OpenAI chat-completions shape, so the conversion from
Anthropic's (system, messages) is mechanical: the system prompt becomes the
first message with role "system".

`effort` is accepted and ignored. It is an Anthropic reasoning-budget knob
with no equivalent here; the roles that pass "none" are asking for cheap and
fast, which is what this backend is throughout.

Env:
  DEEPSEEK_API_KEY            required
  LEARN_DEEPSEEK_MODEL        default deepseek-v4-flash — every role
  LEARN_DEEPSEEK_<ROLE>_MODEL per-role override, e.g. ..._EXAMINER_MODEL
  LEARN_DEEPSEEK_TIMEOUT      default 280 (seconds)
  LEARN_DEEPSEEK_PRICE_IN / _OUT / _CACHED   USD per million tokens
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.deepseek.com/chat/completions"

DEFAULT_MODEL = "deepseek-v4-flash"

# USD per MILLION tokens. These are the one thing in this file that can go
# stale without anything breaking loudly — the number they feed is the running
# "$" in the app header, so a wrong rate shows a wrong spend rather than
# failing. They are overridable precisely so nobody has to edit code to
# correct them: set LEARN_DEEPSEEK_PRICE_IN / _OUT / _CACHED to whatever the
# current published rates are.
PRICE_IN = 0.28
PRICE_OUT = 1.10
PRICE_CACHED = 0.028      # prompt tokens served from DeepSeek's context cache


class DeepSeekError(Exception):
    """Carries an HTTP status so webapi can turn it into an ApiError."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def api_key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "").strip()


def available() -> bool:
    return bool(api_key())


def model_for(role: str) -> str:
    """The model one role runs on. Per-role overrides exist so the judgement
    calls (the examiner, the fact list) can be moved up to deepseek-v4-pro
    without moving the whole conversation with them."""
    per_role = os.environ.get(f"LEARN_DEEPSEEK_{role.upper()}_MODEL", "").strip()
    return per_role or os.environ.get("LEARN_DEEPSEEK_MODEL", "").strip() or DEFAULT_MODEL


def _price(name: str, fallback: float) -> float:
    try:
        return float(os.environ.get(f"LEARN_DEEPSEEK_PRICE_{name}", ""))
    except ValueError:
        return fallback


def usage_cost(usage: dict) -> float:
    """USD for one call. DeepSeek reports cache hits and misses separately;
    when it doesn't, everything falls back to the uncached input rate."""
    if not isinstance(usage, dict):
        return 0.0
    total_in = int(usage.get("prompt_tokens") or 0)
    cached = int(usage.get("prompt_cache_hit_tokens") or 0)
    fresh = usage.get("prompt_cache_miss_tokens")
    fresh = int(fresh) if fresh is not None else max(0, total_in - cached)
    out = int(usage.get("completion_tokens") or 0)
    return (
        fresh * _price("IN", PRICE_IN)
        + cached * _price("CACHED", PRICE_CACHED)
        + out * _price("OUT", PRICE_OUT)
    ) / 1_000_000


def _http_error(exc: "urllib.error.HTTPError", model: str) -> tuple:
    """(message, status) for a failed call, in the app's own vocabulary."""
    try:
        detail = json.loads(exc.read().decode("utf-8"))
        msg = str((detail.get("error") or {}).get("message") or "").strip()
    except Exception:
        msg = ""
    if exc.code == 401:
        return ("DEEPSEEK_API_KEY is missing or invalid on the server", 500)
    if exc.code == 402:
        return ("the DeepSeek account is out of credit", 402)
    if exc.code == 429:
        return ("rate limited by DeepSeek — wait a moment and retry", 429)
    if exc.code == 400 and "model" in msg.lower():
        return (f"DeepSeek rejected the model {model!r}: {msg}", 502)
    return (f"DeepSeek API error {exc.code}{': ' + msg if msg else ''}", 502)


def call_model(system: str, messages: list, role: str,
               effort: "str | None" = None, max_tokens: int = 16000) -> tuple:
    """One completion. Returns (text, cost in USD). Raises DeepSeekError."""
    key = api_key()
    if not key:
        raise DeepSeekError(
            "DEEPSEEK_API_KEY is not set on the server — add it "
            "(`vercel env add DEEPSEEK_API_KEY production`) and redeploy",
            500,
        )
    model = model_for(role)
    payload = {
        "model": model,
        "stream": False,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}] + list(messages),
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST",
    )
    timeout = float(os.environ.get("LEARN_DEEPSEEK_TIMEOUT", "280"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        message, status = _http_error(exc, model)
        raise DeepSeekError(message, status) from exc
    except urllib.error.URLError as exc:
        raise DeepSeekError(f"could not reach the DeepSeek API: {exc.reason}", 502) from exc
    except TimeoutError as exc:
        raise DeepSeekError(f"DeepSeek took longer than {timeout:.0f}s", 504) from exc
    except json.JSONDecodeError as exc:
        raise DeepSeekError("the DeepSeek API returned something unreadable", 502) from exc

    choices = data.get("choices") or []
    if not choices:
        raise DeepSeekError("DeepSeek returned no completion", 502)
    choice = choices[0]
    text = str((choice.get("message") or {}).get("content") or "").strip()
    if not text:
        # a reply cut off by max_tokens is a real failure mode here, and
        # "empty answer" is not a useful thing to show a reader
        if choice.get("finish_reason") == "length":
            raise DeepSeekError(
                "DeepSeek hit the token limit before writing anything — try a "
                "shorter answer length", 502)
        raise DeepSeekError("DeepSeek returned an empty answer", 502)
    return text, usage_cost(data.get("usage"))
