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
ground itself in files on this machine):

  tutor              view + grep + glob, any path, read-only — never shell,
                     never write, never web
  everyone else      no tools at all

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
from pathlib import Path

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
    "--no-custom-instructions",  # keep AGENTS.md etc. out of the personas
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
        flags = ["--available-tools=" + ",".join(READ_TOOLS), "--allow-all-paths"]
        flags += [f"--allow-tool={t}" for t in READ_TOOLS]
        # local grounding starts from the user's home, not this repo
        return flags, str(Path.home())
    # "none" is not a tool name, so the intersection is an empty toolset
    return ["--available-tools=none"], None


def call_model(
    system: str, messages: list, role: str,
    effort: "str | None" = None, max_tokens: int = 16000,
) -> tuple[str, float]:
    prompt = compose_prompt(system, messages)
    flags, cwd = _role_flags(role)
    model = ROLE_MODELS.get(role, "")
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
                     "--add-dir", tmp_holder.name]
            cwd = tmp_holder.name

    cmd = COPILOT_CMD + ["-p", prompt] + _FLAGS_COMMON + flags
    if model:
        cmd += ["--model", model]
    # "none" (the glossary's fast path) means: just don't ask for reasoning
    eff = effort if effort is not None else EFFORT
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
