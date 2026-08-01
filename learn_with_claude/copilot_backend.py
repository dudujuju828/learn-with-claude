"""Model transport that drives the GitHub Copilot CLI non-interactively.

Implements the same ``call_model(system, messages, role, ...)`` seam as the
Anthropic transport in api/index.py, but each call is one ``copilot -p``
subprocess — authenticated by the user's local Copilot login, with no API
key anywhere. Cost is the premium-request count the CLI itself reports
(0 on free-multiplier models).

The CLI has no system-prompt flag and no multi-turn input, so the system
prompt and the full conversation are composed into a single prompt. Prompts
that would blow the Windows command-line length limit are written to a temp
file instead, which the model is told to read with the ``view`` tool.

Per-role tool policy (the whole point of the local mode — the tutor may
ground itself in files, skills, and MCP servers already set up on this
machine — see local_settings.py):

  tutor              view + grep + glob + skill, any path, read-only —
                     never shell, never write, never browse the web —
                     plus whatever of the operator's own already-registered
                     MCP servers (Confluence, say) are turned on, their own
                     AGENTS.md/custom instructions, and an optional shared
                     project directory
  everyone else      no tools, no custom instructions — the learner and
                     glossary personas must stay uncontaminated roleplay,
                     not pick up the operator's own coding instructions

MCP servers are never *defined* here — they're read from (and, for the
one-click Confluence button, written to) the Copilot CLI's own
~/.copilot/mcp-config.json via `copilot mcp list`/`mcp add`, the same config
an interactive `copilot` session on this machine already uses. This app only
remembers which ones the tutor is allowed to reach for (local_settings.py).

Models and effort read the env vars below as a fallback; the settings UI
(local_settings.py, /api/local_settings) overrides them live, without a
restart, via configure()/effective_model()/effective_effort().

Env:
  LEARN_COPILOT_EXE      explicit path to the copilot executable/launcher
  LEARN_COPILOT_MODEL    model for every role (default: the CLI's default)
  LEARN_COPILOT_LEARNER_MODEL / _TUTOR_MODEL / _GLOSSARY_MODEL  per-role override
  LEARN_EFFORT           reasoning effort; leave unset for the CLI default —
                         the default "auto" model rejects effort configuration
  LEARN_TIMEOUT          per-call timeout in seconds (default 300)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from . import copilot_sessions, local_settings, personas
from .webapi import ApiError

# Unlike the API backends this defaults to unset: the CLI's default model
# ("auto") rejects any effort configuration.
EFFORT = os.environ.get("LEARN_EFFORT", "")
TIMEOUT = int(os.environ.get("LEARN_TIMEOUT", "300"))

_MODEL_ALL = os.environ.get("LEARN_COPILOT_MODEL", "")
ROLE_MODELS = {
    "learner": os.environ.get("LEARN_COPILOT_LEARNER_MODEL", _MODEL_ALL),
    "tutor": os.environ.get("LEARN_COPILOT_TUTOR_MODEL", _MODEL_ALL),
    "glossary": os.environ.get("LEARN_COPILOT_GLOSSARY_MODEL", _MODEL_ALL),
}

READ_TOOLS = ["view", "grep", "glob"]

# Live settings overlay, set by localweb.serve() at startup from
# local_settings.json and again whenever the settings UI saves changes — the
# env vars above stay the fallback layer under it. A plain dict + lock is
# enough: one process, and every read takes a snapshot instead of holding
# the lock across a whole request.
_settings_lock = threading.Lock()
_settings = local_settings.default()

# parsed session-memory text, keyed by the anchor file's identity
_memory_lock = threading.Lock()
_memory_cache: dict = {"stamp": None, "text": ""}

# the learner's orientation brief — generated, so cached by how much the
# session has grown rather than by mtime: a live session must not buy a new
# brief every turn just because another sentence was added
BRIEF_REFRESH_CHARS = 6000
BRIEF_REFRESH_RATIO = 0.25
_brief_lock = threading.Lock()
_brief_cache: dict = {"session": "", "size": 0, "text": ""}


def configure(settings: dict) -> None:
    """Install a new live settings overlay. `settings` must already be
    sanitized (local_settings.sanitize/LocalSettingsStore.load do that)."""
    global _settings
    with _settings_lock:
        _settings = settings


def _snapshot() -> dict:
    with _settings_lock:
        return _settings


def effective_model(role: str) -> str:
    """The model actually used for `role`: a live override, else the
    LEARN_COPILOT_*_MODEL env var, else "" (the CLI's own "auto").

    The examiner (the written exam's paper-setter and marker) and the fact
    lister have no settings entry of their own — locally there is no
    per-token bill to protect, so they ride the tutor's model rather than
    adding dropdowns nobody would have a reason to set differently."""
    if role in ("examiner", "facts"):
        role = "tutor"
    return _snapshot()["models"].get(role, "") or ROLE_MODELS.get(role, "")


def effective_effort() -> str:
    return _snapshot()["effort"] or EFFORT


def session_memory() -> str:
    """The tutor's memory block for the anchored Copilot session, or "".

    The transcript is re-read only when the session file actually changes
    (it's append-only, so size+mtime identify it), since a long session can
    run to hundreds of KB and this is called on every single tutor turn."""
    session_id = _snapshot()["tutor_session"]
    if not session_id:
        return ""
    try:
        st = copilot_sessions.session_root().joinpath(session_id, "events.jsonl").stat()
        stamp = (session_id, st.st_size, st.st_mtime)
    except OSError:
        return ""     # the session was deleted since it was chosen
    with _memory_lock:
        if _memory_cache.get("stamp") == stamp:
            return _memory_cache["text"]
    transcript = copilot_sessions.transcript(session_id)
    text = personas.session_memory_system(transcript) if transcript else ""
    with _memory_lock:
        _memory_cache["stamp"], _memory_cache["text"] = stamp, text
    return text


def learner_brief() -> tuple:
    """(orientation brief, cost) for the anchored session — or ("", 0.0).

    The tutor gets the session verbatim; the learner must NOT. It drives every
    question, so it needs to recognise the domain's vocabulary or it misreads
    a term and aims the whole investigation somewhere useless — but hand it
    the transcript and it stops being ignorant, which is the one thing that
    makes this tool work. So it gets a generated brief: the names in play and
    what kind of thing each is, never the explanations.

    Generated once on the cheap model and cached. A session that is still
    running would otherwise re-generate every single turn, so a grown session
    only earns a fresh brief once it has moved materially — the vocabulary of
    a domain doesn't change every time somebody asks another question.
    """
    session_id = _snapshot()["tutor_session"]
    if not session_id:
        return "", 0.0
    transcript = copilot_sessions.transcript(session_id)
    if not transcript:
        return "", 0.0
    size = len(transcript)
    with _brief_lock:
        cached = dict(_brief_cache)
    if cached.get("session") == session_id and cached.get("text"):
        grew = size - cached["size"]
        if grew < max(BRIEF_REFRESH_CHARS, cached["size"] * BRIEF_REFRESH_RATIO):
            return cached["text"], 0.0
    try:
        text, cost = call_model(
            personas.SESSION_BRIEF_SYSTEM,
            [{"role": "user", "content": personas.session_brief_message(transcript)}],
            "glossary", effort="none", max_tokens=1200,
        )
    except ApiError:
        # no brief is survivable; a failed investigation is not
        return cached.get("text", "") if cached.get("session") == session_id else "", 0.0
    text = text.strip()
    with _brief_lock:
        _brief_cache.update(session=session_id, size=size, text=text)
    return text, cost


def grounding_text() -> str:
    """The tutor's local-grounding system-prompt block for the CURRENT
    settings. Called fresh per request (never cached) since code_dir, the MCP
    server list, and the anchored session can all change while the server
    keeps running."""
    settings = _snapshot()
    notes = [f'{s["name"]} — {s["note"]}' if s.get("note") else s["name"]
             for s in settings["mcp_servers"] if s.get("enabled")]
    blocks = [personas.local_grounding_system(settings["code_dir"] or None, notes)]
    memory = session_memory()
    if memory:
        blocks.append(memory)
    return "\n\n".join(blocks)


def _enabled_server_names() -> list:
    return [s["name"] for s in _snapshot()["mcp_servers"] if s.get("enabled")]


def list_global_mcp_servers() -> list:
    """Every MCP server this Copilot CLI installation already knows about —
    from ~/.copilot/mcp-config.json (source "user"), a workspace .mcp.json,
    or a plugin — as [{"name", "type", "source", ...}]. This is what the
    settings panel's checklist renders; nothing here is ever written by this
    app except through add_global_mcp_server(). Empty list (never raises) if
    the CLI can't answer — a fresh install with nothing configured yet, or
    verify_copilot() never having run, both look the same to the panel: no
    servers to turn on."""
    try:
        proc = subprocess.run(
            COPILOT_CMD + ["mcp", "list", "--json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    try:
        servers = json.loads(proc.stdout or "{}").get("mcpServers") or {}
    except json.JSONDecodeError:
        return []
    if not isinstance(servers, dict):
        return []
    return [{"name": name, **(cfg if isinstance(cfg, dict) else {})}
            for name, cfg in servers.items()]


def add_global_mcp_server(name: str, *, transport: str, url: str,
                          headers: "dict | None" = None) -> None:
    """`copilot mcp add` for a remote (http/sse) server — used by the
    settings panel's one-click Confluence button. Writes to the user's own
    ~/.copilot/mcp-config.json, same as if they'd typed the command
    themselves; this app never manages a second, competing definition of it.
    (Only remote servers so far — nothing in this app registers a local
    stdio server on someone's behalf.)"""
    cmd = COPILOT_CMD + ["mcp", "add", "--transport", transport]
    for k, v in (headers or {}).items():
        cmd += ["--header", f"{k}: {v}"]
    cmd += [name, url]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ApiError(f"could not run the Copilot CLI: {exc}", 500)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:300]
        raise ApiError(f'"copilot mcp add" failed: {detail}', 502)


# Windows CreateProcess caps the whole command line at ~32K chars; beyond this
# the prompt travels via a temp file the model reads with `view` instead.
ARGV_PROMPT_LIMIT = 25000

_FLAGS_COMMON = [
    # JSONL events, not plain text: when the tutor uses tools, `-s` would glue
    # its "let me look at..." narration onto the answer; the event stream keeps
    # the final message separate, and carries the real premium-request count.
    "--output-format", "json",
    "--no-color",
    "--log-level", "none",
    "--no-auto-update",
    "--disable-builtin-mcps",    # no GitHub MCP server — no GitHub API traffic
    "--no-remote-export",        # sessions stay on this machine
    "--no-ask-user",
]


def _npm_loader() -> "list[str] | None":
    """Invoke node + the package entry directly: the .cmd shim would drag in
    cmd.exe and its own, much smaller, command-line length limit."""
    node = shutil.which("node")
    appdata = os.environ.get("APPDATA")
    if not (node and appdata):
        return None
    loader = Path(appdata) / "npm" / "node_modules" / "@github" / "copilot" / "npm-loader.js"
    return [node, str(loader)] if loader.is_file() else None


def resolve_copilot() -> list[str]:
    """The argv prefix that runs the real Copilot CLI (the VS Code extension
    ships a same-named launcher stub that must not win)."""
    exe = os.environ.get("LEARN_COPILOT_EXE")
    if exe:
        return [exe]
    return _npm_loader() or [shutil.which("copilot") or "copilot"]


COPILOT_CMD = resolve_copilot()


def verify_copilot() -> str:
    """Run once at server start: confirm the resolved thing is the actual CLI
    (and implicitly that node works). Returns the version line."""
    try:
        proc = subprocess.run(
            COPILOT_CMD + ["--version"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60, stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"could not run the Copilot CLI ({' '.join(COPILOT_CMD)}): {exc}\n"
            "Install it with:  npm install -g @github/copilot"
        )
    line = (proc.stdout or proc.stderr or "").strip().splitlines()[0] if (proc.stdout or proc.stderr) else ""
    if proc.returncode != 0 or not re.search(r"Copilot CLI \d", line):
        raise RuntimeError(
            f"'{' '.join(COPILOT_CMD)}' is not the GitHub Copilot CLI (got: {line!r}).\n"
            "Install it with:  npm install -g @github/copilot   (then run `copilot` once to log in)"
        )
    return line


def compose_prompt(system: str, messages: list) -> str:
    lines = []
    if system:
        lines += ["=== SYSTEM INSTRUCTIONS (these govern your reply) ===", system.strip(), ""]
    lines.append("=== CONVERSATION SO FAR (you are `assistant`) ===")
    for m in messages:
        lines.append(f"\n[{m['role']}]:\n{m['content']}")
    lines += [
        "",
        "=== YOUR TASK ===",
        "Write the assistant's next reply to the last user message above, "
        "following the system instructions exactly.",
        "Output only the reply itself — no role label, no preamble, no notes "
        "about tools or process.",
    ]
    return "\n".join(lines)


def _role_flags(role: str) -> tuple[list[str], "str | None"]:
    """(extra argv, working directory) for one persona's tool surface."""
    if role == "tutor":
        tools = READ_TOOLS + ["skill"] + _enabled_server_names()
        flags = ["--available-tools=" + ",".join(tools), "--allow-all-paths"]
        flags += [f"--allow-tool={t}" for t in tools]
        code_dir = _snapshot()["code_dir"]
        if code_dir:
            flags += ["--add-dir", code_dir]
        # local grounding starts from the user's home, not this repo. Custom
        # instructions (AGENTS.md etc.) stay ON for the tutor deliberately —
        # this is the one role meant to answer like the operator's own
        # Copilot setup would, not a fixed persona.
        return flags, str(Path.home())
    # "none" is not a tool name, so the intersection is an empty toolset;
    # the learner/glossary personas must never pick up the operator's own
    # coding instructions — they're a fixed roleplay, not a coding assistant.
    return ["--available-tools=none", "--no-custom-instructions"], None


def call_model(
    system: str, messages: list, role: str,
    effort: "str | None" = None, max_tokens: int = 16000,
) -> tuple[str, float]:
    prompt = compose_prompt(system, messages)
    flags, cwd = _role_flags(role)
    model = effective_model(role)
    tmp_holder = None

    if len(prompt) > ARGV_PROMPT_LIMIT:
        # overflow: park the composed prompt in a private temp dir and let the
        # model read it — `view` on that one directory is the only tool added
        tmp_holder = tempfile.TemporaryDirectory(prefix="learn-copilot-")
        ppath = Path(tmp_holder.name) / "prompt.md"
        ppath.write_text(prompt, encoding="utf-8")
        prompt = (
            f"Read the file {ppath} with the view tool. It contains system "
            "instructions and a conversation; do what its 'YOUR TASK' section "
            "says. Output only the reply itself."
        )
        if role != "tutor":
            flags = ["--available-tools=view", "--allow-tool=view",
                     "--add-dir", tmp_holder.name, "--no-custom-instructions"]
            cwd = tmp_holder.name

    cmd = COPILOT_CMD + ["-p", prompt] + _FLAGS_COMMON + flags
    if model:
        cmd += ["--model", model]
    # "none" (the glossary's fast path) means: just don't ask for reasoning
    eff = effort if effort is not None else effective_effort()
    if eff and eff != "none":
        cmd += ["--effort", eff]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TIMEOUT, cwd=cwd, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ApiError(f"copilot timed out after {TIMEOUT}s", 504)
    except OSError as exc:
        raise ApiError(f"could not run the Copilot CLI: {exc}", 500)
    finally:
        if tmp_holder is not None:
            tmp_holder.cleanup()

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:500]
        raise ApiError(f"copilot exited {proc.returncode}: {detail}", 502)
    return _parse_stream(proc.stdout or "")


def _parse_stream(stdout: str) -> tuple[str, float]:
    """The final assistant message + the premium requests actually billed,
    out of the JSONL event stream."""
    text, cost = "", 0.0
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        data = event.get("data") or {}
        if event.get("type") == "assistant.message" and isinstance(data, dict):
            text = str(data.get("content") or "")
        elif event.get("type") == "result":
            usage = event.get("usage") or {}
            if isinstance(usage, dict):
                cost = float(usage.get("premiumRequests") or 0.0)
    text = text.strip()
    if not text:
        raise ApiError("copilot returned an empty reply", 502)
    return text, cost
