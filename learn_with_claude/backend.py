"""Thin wrapper around the `claude` CLI used as a conversation backend.

Each :class:`ClaudeSession` is one persistent claude-code conversation. The
first message establishes the system prompt; every later message resumes the
same session by id so context carries over.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

# Resolve the claude executable once. On this machine it is a native .EXE, so it
# can be invoked as a plain argument list (no shell, no quoting headaches).
CLAUDE_EXE = shutil.which("claude") or "claude"


class ClaudeError(RuntimeError):
    """Raised when the claude CLI fails or returns something unparseable."""


@dataclass
class Reply:
    text: str
    cost_usd: float
    session_id: str
    raw: dict = field(repr=False)


class ClaudeSession:
    """A single persistent `claude -p` conversation.

    Parameters
    ----------
    system_prompt:
        Fully *overrides* claude-code's default system prompt (``--system-prompt``).
        Used to install a clean persona with none of the coding-agent baggage.
    model:
        Model alias or full id (e.g. ``"sonnet"``, ``"opus"``, ``"claude-sonnet-5"``).
    effort:
        Reasoning effort for the session (``low``/``medium``/``high``/``xhigh``/``max``).
    exclude_dynamic:
        Strip the dynamic system-prompt sections (env, dir listing, CLAUDE.md …)
        so the persona stays clean and reproducible.
    builtin_tools:
        Value for ``--tools``. Personas are conversational, so the default is
        ``""`` — no filesystem/bash access.
    """

    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        model: str = "sonnet",
        effort: str | None = None,
        exclude_dynamic: bool = True,
        timeout: int = 300,
        builtin_tools: str = "",
    ) -> None:
        self.system_prompt = system_prompt
        self.model = model
        self.effort = effort
        self.exclude_dynamic = exclude_dynamic
        self.timeout = timeout
        self.builtin_tools = builtin_tools

        self.session_id: str | None = None
        self.total_cost: float = 0.0
        self.turns: int = 0

    def send(self, message: str) -> Reply:
        """Send one message and return the tutor/learner's reply."""
        # Every send is a fresh claude process, so session-level flags (model,
        # effort, tool surface, MCP servers) must be repeated on every call —
        # only the conversation itself is carried over via --resume.
        cmd = [
            CLAUDE_EXE,
            "-p",
            message,
            "--output-format",
            "json",
            "--model",
            self.model,
            "--tools",
            self.builtin_tools,
            "--strict-mcp-config",
        ]
        if self.effort:
            cmd += ["--effort", self.effort]

        if self.session_id is None:
            # First turn: install the persona / system prompt.
            if self.system_prompt:
                cmd += ["--system-prompt", self.system_prompt]
            if self.exclude_dynamic:
                cmd += ["--exclude-dynamic-system-prompt-sections"]
        else:
            # Subsequent turns: resume the same conversation.
            cmd += ["--resume", self.session_id]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout,
                stdin=subprocess.DEVNULL,  # never let claude consume the shell's stdin
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing dependent
            raise ClaudeError(f"claude timed out after {self.timeout}s") from exc

        if proc.returncode != 0:
            raise ClaudeError(
                f"claude exited {proc.returncode}: {(proc.stderr or '').strip()[:500]}"
            )

        try:
            env = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeError(
                f"could not parse claude output: {proc.stdout[:500]!r}"
            ) from exc

        if env.get("is_error"):
            raise ClaudeError(f"claude returned an error: {env.get('result')!r}")

        self.session_id = env.get("session_id", self.session_id)
        cost = float(env.get("total_cost_usd") or 0.0)
        self.total_cost += cost
        self.turns += 1

        return Reply(
            text=(env.get("result") or "").strip(),
            cost_usd=cost,
            session_id=self.session_id or "",
            raw=env,
        )
