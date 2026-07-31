"""Read the Copilot CLI's own past sessions, so one of them can seed the
tutor's memory.

When you leave an interactive ``copilot`` session it tells you how to pick it
up again (``copilot --resume <id>``). This module lets ``learn --web`` use one
of those sessions as the tutor's *starting memory*: whatever you and Copilot
worked through in it — a codebase you explored, a design you argued out, a
document you read together — is already known to the tutor when you start
asking about it here.

**Why read the transcript instead of just passing ``--resume``.** Resuming
does work with ``-p``, but it *appends* to the session: every call would write
this app's composed prompt (which already replays the whole conversation) back
into the session you wanted to keep as a fixed starting point, so it would
grow without bound, duplicate itself turn after turn, and leave your own
session full of learn-with-claude scaffolding. Measured: one trivial ``-p
--resume`` call doubled a session's ``events.jsonl``. The tutor's transport
here is one stateless subprocess per call, so the honest fit is to read the
session once, distil it to a bounded transcript, and hand that to the tutor as
memory — the anchor session is opened read-only and never written to.

The layout below (``$COPILOT_HOME/session-state/<id>/events.jsonl``, one JSON
event per line) is the CLI's own private format, not a published interface, so
every read here is defensive: anything unparseable is skipped, and a session
that can't be read at all simply yields no memory rather than an error.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# a session id is a uuid; we also accept a unique prefix, which is what the
# CLI itself accepts for --resume
SESSION_REF = re.compile(r"^[0-9a-fA-F][0-9a-fA-F-]{3,63}$")

# how much of a session can become tutor memory. Long coding sessions run to
# hundreds of KB; past this the middle is elided, keeping how it started and
# where it ended up — the two parts that actually carry the context.
TRANSCRIPT_BUDGET = 16000
HEAD_MESSAGES = 2
MAX_MESSAGE = 4000


def session_root() -> Path:
    """Where the CLI keeps its sessions, honouring COPILOT_HOME."""
    home = os.environ.get("COPILOT_HOME")
    return (Path(home) if home else Path.home() / ".copilot") / "session-state"


def _events_path(session_id: str) -> Path:
    return session_root() / session_id / "events.jsonl"


def _messages(path: Path) -> list:
    """[{role, text}] for the human-readable turns of one session.

    Only ``user.message`` / ``assistant.message`` carry conversation; tool
    calls, reasoning blobs, and the ephemeral session chatter are skipped, as
    are the turns where the assistant only called a tool and said nothing.
    """
    out = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = event.get("type")
                if kind not in ("user.message", "assistant.message"):
                    continue
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                # "content" is what was actually said; "transformedContent"
                # carries the CLI's own injected preamble, which isn't ours
                text = str(data.get("content") or "").strip()
                if not text:
                    continue
                out.append({"role": "user" if kind == "user.message" else "assistant",
                            "text": text[:MAX_MESSAGE]})
    except OSError:
        return []
    return out


def resolve(ref: str) -> "str | None":
    """The full session id for `ref` — an exact id, or a prefix that matches
    exactly one session. None if it matches nothing or is ambiguous."""
    ref = (ref or "").strip().lower()
    if not ref or not SESSION_REF.match(ref):
        return None
    root = session_root()
    if (root / ref / "events.jsonl").is_file():
        return ref
    try:
        hits = [d.name for d in root.iterdir()
                if d.is_dir() and d.name.lower().startswith(ref)
                and (d / "events.jsonl").is_file()]
    except OSError:
        return None
    return hits[0] if len(hits) == 1 else None


def describe(session_id: str) -> "dict | None":
    """{id, when, messages, title} for one session — what the settings panel
    shows so you can tell you picked the right one."""
    path = _events_path(session_id)
    if not path.is_file():
        return None
    msgs = _messages(path)
    first = next((m["text"] for m in msgs if m["role"] == "user"), "")
    try:
        when = path.stat().st_mtime
    except OSError:
        when = 0
    return {
        "id": session_id,
        "when": when,
        "messages": len(msgs),
        "title": " ".join(first.split())[:120],
    }


# This app's own model calls are sessions too, and on a machine that has run
# `learn --web` for a while they vastly outnumber the real ones. They open with
# compose_prompt()'s banner (or, for an over-long prompt, its temp-file
# instruction), which is how the picker tells them apart and hides them —
# resuming the tutor's memory from one of its own one-shot calls is never what
# anyone means.
_OWN_CALL_MARKERS = (
    "=== SYSTEM INSTRUCTIONS",
    "=== CONVERSATION SO FAR",
    "Read the file ",
)


def _is_own_call(title: str) -> bool:
    return any(title.startswith(m) for m in _OWN_CALL_MARKERS)


def recent(limit: int = 12) -> list:
    """The most recently touched sessions that actually hold a conversation
    someone had, newest first — the picker's contents."""
    try:
        dirs = [d for d in session_root().iterdir() if d.is_dir()]
    except OSError:
        return []

    def touched(d: Path) -> float:
        try:
            return (d / "events.jsonl").stat().st_mtime
        except OSError:
            return 0.0

    out = []
    for d in sorted(dirs, key=touched, reverse=True):
        if len(out) >= limit:
            break
        info = describe(d.name)
        if info and info["messages"] and not _is_own_call(info["title"]):
            out.append(info)
    return out


def transcript(session_id: str, budget: int = TRANSCRIPT_BUDGET) -> str:
    """The session as a plain transcript, trimmed to `budget` characters.

    Over budget, the opening exchange is kept and the middle elided: how the
    session was framed matters as much as where it ended up, and the tail is
    where the conclusions live. Empty string if there's nothing readable —
    callers treat that as "no memory", never as an error.
    """
    msgs = _messages(_events_path(session_id))
    if not msgs:
        return ""
    blocks = [f"[{m['role']}]\n{m['text']}" for m in msgs]
    total = sum(len(b) + 2 for b in blocks)
    if total <= budget:
        return "\n\n".join(blocks)

    head = blocks[:HEAD_MESSAGES]
    used = sum(len(b) + 2 for b in head)
    tail = []
    for block in reversed(blocks[HEAD_MESSAGES:]):
        if used + len(block) + 2 > budget:
            break
        tail.append(block)
        used += len(block) + 2
    tail.reverse()
    skipped = len(blocks) - len(head) - len(tail)
    middle = [f"[… {skipped} messages omitted …]"] if skipped > 0 else []
    return "\n\n".join(head + middle + tail)
