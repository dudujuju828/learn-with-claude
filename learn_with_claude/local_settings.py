"""Local-only settings for the Copilot CLI transport.

Lets someone running ``learn --web`` swap the model per role, pick a
reasoning effort, point the tutor at a directory of their own code or notes,
and choose which of their own already-registered MCP servers (Confluence,
notably) the tutor may call on before answering. Persisted as one small JSON
document beside the knowledge dir (``local_settings.json``, next to
``tutors.json``) so it survives restarts.

MCP servers are NOT defined here — they live in the Copilot CLI's own
``~/.copilot/mcp-config.json`` (edited via ``copilot mcp add``, or the
one-click Confluence button, which shells out to the same command). This
file only remembers which of those already-registered servers are turned on
for the tutor, plus an optional note describing each one to the tutor —
deliberately not a second place to define what a server IS.

Irrelevant to, and never imported by, the hosted Vercel backend (api/index.py)
— that transport has no local filesystem, MCP, or skills story at all.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import copilot_sessions

EFFORT_CHOICES = {"", "none", "minimal", "low", "medium", "high", "xhigh", "max"}
ROLES = ("learner", "tutor", "glossary")

_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_MODEL_LEN = 80
MAX_SERVERS = 20
MAX_NOTE_LEN = 200

# Args `copilot mcp add` needs to register Atlassian's own remote MCP server:
# one URL, OAuth 2.1 handled by the CLI itself on first use (a browser tab
# opens to sign in) — no API token to type in or store here. Covers
# Confluence *and* Jira on Atlassian Cloud; self-hosted Confluence needs a
# different (stdio, token-based) server, which someone can register with
# `copilot mcp add` themselves like any other — it'll show up in the
# settings panel's checklist same as this one does.
CONFLUENCE_PRESET = {
    "name": "confluence",
    "transport": "http",
    "url": "https://mcp.atlassian.com/v1/mcp/authv2",
    "note": "the team's Confluence/Jira wiki (Atlassian's official remote MCP "
            "— first use opens a browser tab to sign in, nothing to type here)",
}


def default() -> dict:
    return {
        "models": {"learner": "", "tutor": "", "glossary": ""},
        "effort": "",
        "code_dir": "",
        "tutor_session": "",
        "mcp_servers": [],
    }


def _clean_server_ref(raw: dict, *, strict: bool) -> "dict | None":
    """One {name, enabled, note} entry — a reference to a server already
    registered in ~/.copilot/mcp-config.json, not a definition of one."""
    if not isinstance(raw, dict):
        if strict:
            raise ValueError("each mcp server entry must be an object")
        return None
    name = str(raw.get("name") or "").strip().lower()
    if not _NAME.match(name):
        if strict:
            raise ValueError(
                f"server name {name!r} must be lowercase letters/digits/hyphens, "
                "starting with a letter"
            )
        return None
    return {
        "name": name,
        "enabled": bool(raw.get("enabled", True)),
        "note": str(raw.get("note") or "").strip()[:MAX_NOTE_LEN],
    }


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

    # the Copilot session whose transcript seeds the tutor's memory. Saving
    # resolves a pasted prefix to the full id (and rejects one that matches
    # nothing or several); loading keeps whatever is on disk even if that
    # session has since been deleted — the panel reports it as missing and the
    # tutor simply gets no memory, which beats refusing to start.
    session = str(doc.get("tutor_session") or "").strip().lower()
    if session:
        if strict:
            full = copilot_sessions.resolve(session)
            if not full:
                raise ValueError(
                    f'no Copilot session matches "{session}" — paste the id it '
                    "printed when you left the session (a unique prefix is fine)"
                )
            out["tutor_session"] = full
        elif copilot_sessions.SESSION_REF.match(session):
            out["tutor_session"] = session

    raw_servers = doc.get("mcp_servers")
    if raw_servers is not None and not isinstance(raw_servers, list):
        if strict:
            raise ValueError("mcp_servers must be a list")
        raw_servers = []
    if strict and len(raw_servers or []) > MAX_SERVERS:
        raise ValueError(f"at most {MAX_SERVERS} mcp servers")
    servers, seen = [], set()
    for raw in (raw_servers or [])[:MAX_SERVERS]:
        s = _clean_server_ref(raw, strict=strict)
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
