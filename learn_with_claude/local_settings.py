"""Local-only settings for the Copilot CLI transport.

Lets someone running ``learn --web`` swap the model per role, pick a
reasoning effort, point the tutor at a directory of their own code or notes,
and wire up MCP servers (Confluence, notably) the tutor may call on before
answering. Persisted as one small JSON document beside the knowledge dir
(``local_settings.json``, next to ``tutors.json``) so it survives restarts.

Irrelevant to, and never imported by, the hosted Vercel backend (api/index.py)
— that transport has no local filesystem or MCP story at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

EFFORT_CHOICES = {"", "none", "minimal", "low", "medium", "high", "xhigh", "max"}
TRANSPORTS = {"stdio", "http", "sse"}
ROLES = ("learner", "tutor", "glossary")

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_MODEL_LEN = 80
MAX_SERVERS = 8
MAX_ARGS = 20
MAX_KV = 20
MAX_VAL_LEN = 400
MAX_NOTE_LEN = 200

# Atlassian's own remote MCP server: one URL, OAuth 2.1 handled by the
# Copilot CLI itself on first use (a browser tab opens to sign in) — no API
# token to type in or store. Covers Confluence *and* Jira on Atlassian Cloud;
# self-hosted Confluence needs a different (stdio, token-based) server, which
# is exactly what the free-form "advanced config" on a custom row is for.
CONFLUENCE_PRESET = {
    "name": "confluence",
    "transport": "http",
    "url": "https://mcp.atlassian.com/v1/mcp/authv2",
    "headers": {},
    "note": "the team's Confluence/Jira wiki (Atlassian's official remote MCP "
            "— first use opens a browser tab to sign in, nothing to type here)",
}


def default() -> dict:
    return {
        "models": {"learner": "", "tutor": "", "glossary": ""},
        "effort": "",
        "code_dir": "",
        "mcp_servers": [],
    }


def _clean_kv(raw, *, max_items: int) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for k, v in list(raw.items())[:max_items]:
        key = str(k).strip()[:64]
        if key:
            out[key] = str(v)[:MAX_VAL_LEN]
    return out


def _clean_server(raw: dict, *, strict: bool) -> "dict | None":
    """One MCP server entry, or None if invalid (and not strict)."""
    if not isinstance(raw, dict):
        if strict:
            raise ValueError("each mcp server must be an object")
        return None
    name = str(raw.get("name") or "").strip().lower()
    if not _NAME.match(name):
        if strict:
            raise ValueError(
                f"server name {name!r} must be lowercase letters/digits/hyphens, "
                "starting with a letter"
            )
        return None
    transport = str(raw.get("transport") or "stdio").strip().lower()
    if transport not in TRANSPORTS:
        if strict:
            raise ValueError(f'server "{name}": transport must be stdio, http, or sse')
        return None
    out = {
        "name": name,
        "transport": transport,
        "enabled": bool(raw.get("enabled", True)),
        "note": str(raw.get("note") or "").strip()[:MAX_NOTE_LEN],
    }
    if transport == "stdio":
        command = str(raw.get("command") or "").strip()
        if not command:
            if strict:
                raise ValueError(f'server "{name}": a stdio server needs a command')
            return None
        out["command"] = command
        out["args"] = [str(a).strip() for a in (raw.get("args") or [])
                       if str(a).strip()][:MAX_ARGS]
        out["env"] = _clean_kv(raw.get("env"), max_items=MAX_KV)
    else:
        url = str(raw.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            if strict:
                raise ValueError(f'server "{name}": needs an http(s):// url')
            return None
        out["url"] = url
        out["headers"] = _clean_kv(raw.get("headers"), max_items=MAX_KV)
    return out


def sanitize(doc, *, strict: bool = False) -> dict:
    """Coerce `doc` into a valid settings dict.

    ``strict=False`` (the load path) drops anything bad — a hand-edited or
    stale file must never stop the server from starting. ``strict=True`` (the
    save path, driven by the settings UI) raises ``ValueError`` with a message
    fit to show the person who typed the bad value.
    """
    out = default()
    if not isinstance(doc, dict):
        if strict:
            raise ValueError("settings must be an object")
        return out

    models = doc.get("models")
    if models is not None and not isinstance(models, dict):
        if strict:
            raise ValueError("models must be an object")
        models = {}
    for role in ROLES:
        m = str((models or {}).get(role) or "").strip()
        if strict and len(m) > MAX_MODEL_LEN:
            raise ValueError(f'"{role}" model name is too long')
        out["models"][role] = m[:MAX_MODEL_LEN]

    effort = str(doc.get("effort") or "").strip().lower()
    if effort not in EFFORT_CHOICES:
        if strict:
            raise ValueError(f'effort must be one of: {", ".join(sorted(EFFORT_CHOICES)) or "(default)"}')
        effort = ""
    out["effort"] = effort

    code_dir = str(doc.get("code_dir") or "").strip()
    if code_dir:
        p = Path(code_dir).expanduser()
        if not p.is_dir():
            if strict:
                raise ValueError(f'"{code_dir}" is not a directory on this machine')
        else:
            out["code_dir"] = str(p.resolve())

    raw_servers = doc.get("mcp_servers")
    if raw_servers is not None and not isinstance(raw_servers, list):
        if strict:
            raise ValueError("mcp_servers must be a list")
        raw_servers = []
    if strict and len(raw_servers or []) > MAX_SERVERS:
        raise ValueError(f"at most {MAX_SERVERS} mcp servers")
    servers, seen = [], set()
    for raw in (raw_servers or [])[:MAX_SERVERS]:
        s = _clean_server(raw, strict=strict)
        if s is None:
            continue
        if s["name"] in seen:
            if strict:
                raise ValueError(f'duplicate server name "{s["name"]}"')
            continue
        seen.add(s["name"])
        servers.append(s)
    out["mcp_servers"] = servers
    return out


class LocalSettingsStore:
    """One JSON document on disk; sanitize() guards every read and write."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict:
        try:
            return sanitize(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return default()

    def save(self, doc: dict) -> dict:
        clean = sanitize(doc, strict=True)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")
        return clean
