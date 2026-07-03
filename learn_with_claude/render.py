"""Terminal rendering, tuned for dyslexia-friendly readability.

Design choices that help (within what a terminal program can control):
  * short line length (~64 chars) — long lines are hard to track;
  * sentence case, never ALL CAPS;
  * high-contrast body text (the terminal's own default colour), with colour used
    only on labels and a left "gutter" bar so each block is a clear visual chunk;
  * generous blank-line spacing between blocks and turns;
  * tutor answers reflowed to one sentence per paragraph, blank line between
    sentences (see `space_sentences`);
  * no italics, no low-contrast dim body text.
The actual *font* is a terminal setting we can't change here — use the HTML export
for a dyslexic typeface.
"""

from __future__ import annotations

import os
import re
import sys
import textwrap

# A sentence end (. ! ?), optionally followed by closing quotes/brackets, then
# whitespace, then something that looks like a new sentence starting.
_SENTENCE_GAP = re.compile(r"(?<=[.!?])([\"')\]]*)\s+(?=[A-Z0-9\"'(\[])")
_CODE_FENCE = re.compile(r"(```[^\n]*\n.*?(?:```|\Z))", re.S)


def space_sentences(text: str) -> str:
    """Reflow prose so every sentence sits in its own paragraph with a blank
    line between them — much easier to track for dyslexic readers. Fenced code
    blocks are left untouched. Idempotent, so it is safe to apply both when a
    reply is recorded and again when old saved trees are re-displayed."""
    parts = _CODE_FENCE.split(text or "")
    for i in range(0, len(parts), 2):  # even indices are prose between fences
        parts[i] = _SENTENCE_GAP.sub(r"\1\n\n", parts[i])
    return "".join(parts).strip()


class Palette:
    """ANSI colour codes, or empty strings when colour is disabled."""

    def __init__(self, enabled: bool) -> None:
        codes = {
            "reset": "\033[0m",
            "dim": "\033[2m",
            "bold": "\033[1m",
            "cyan": "\033[36m",
            "blue": "\033[94m",
            "green": "\033[92m",
            "yellow": "\033[93m",
            "magenta": "\033[95m",
            "grey": "\033[90m",
        }
        for name, code in codes.items():
            setattr(self, name, code if enabled else "")


def prepare_console() -> None:
    """Best-effort: enable ANSI handling and force UTF-8 output on Windows."""
    if os.name == "nt":
        os.system("")  # toggles ENABLE_VIRTUAL_TERMINAL_PROCESSING for this console
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def wrap_paragraphs(text: str, width: int) -> list[str]:
    """Wrap prose to `width`, but leave fenced code blocks intact so code keeps
    its formatting. Returns a flat list of display lines."""
    lines: list[str] = []
    in_code = False
    for raw in (text or "").splitlines():
        if raw.lstrip().startswith("```"):
            in_code = not in_code
            lines.append(raw)
        elif in_code:
            lines.append(raw)
        elif not raw.strip():
            lines.append("")
        else:
            lines.extend(textwrap.fill(raw, width=width).splitlines())
    return lines or [""]


class Renderer:
    def __init__(self, color: bool = True, width: int = 66, spacing: int = 1) -> None:
        self.c = Palette(color)
        self.width = max(40, width)
        self.spacing = max(1, spacing)  # 1 = single, 2 = extra blank line between lines

    # --- transient status line -------------------------------------------
    def status(self, msg: str) -> None:
        c = self.c
        sys.stdout.write(f"\r{c.grey}  · {msg}{c.reset}\033[K")
        sys.stdout.flush()

    def clear_status(self) -> None:
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    # --- low-level building blocks ---------------------------------------
    def _rule(self, label: str) -> None:
        c = self.c
        dashes = "─" * max(4, self.width - len(label) - 4)
        print()
        print(f"{c.cyan}──{c.reset} {c.bold}{c.cyan}{label}{c.reset} {c.cyan}{dashes}{c.reset}")
        print()

    def _emit_block(self, label: str, lines: list[str], color: str, meta: str = "") -> None:
        """A labelled block with a coloured left gutter and default-colour body
        text (max contrast)."""
        c = self.c
        head = f"{color}{c.bold}{label}{c.reset}"
        if meta:
            head += f"  {c.grey}{meta}{c.reset}"
        print(head)
        for ln in lines:
            print(f"{color}│{c.reset} {ln}")
            for _ in range(self.spacing - 1):
                print(f"{color}│{c.reset}")
        print()

    # --- a learner turn --------------------------------------------------
    def learner(self, turn: int, thinking: str, new_term: str, action: str, confidence) -> None:
        c = self.c
        self._rule(f"Turn {turn}")
        if thinking:
            meta = f"(confidence {confidence}%)" if confidence is not None else ""
            self._emit_block("💭 Thinking to myself", wrap_paragraphs(thinking, self.width - 2),
                             c.yellow, meta)
        if new_term:
            print(f"{c.magenta}{c.bold}🔍 New word I hit:{c.reset} {c.magenta}{new_term}{c.reset}")
            print()
        self._emit_block("🙋 I ask Claude", wrap_paragraphs(action, self.width - 2), c.green)

    def tutor(self, text: str) -> None:
        text = space_sentences(text)
        self._emit_block("📘 Claude answers", wrap_paragraphs(text, self.width - 2), self.c.blue)

    # --- shell chrome ----------------------------------------------------
    def shell_banner(self, knowledge_dir) -> None:
        c = self.c
        bar = "═" * self.width
        print(f"{c.cyan}{bar}{c.reset}")
        print(f"{c.bold}{c.cyan}  Learn with Claude  ·  knowledge shell{c.reset}")
        print(f"{c.grey}  Knowledge dir: {knowledge_dir}   ·   type 'help' for commands{c.reset}")
        print(f"{c.cyan}{bar}{c.reset}")

    def section(self, title: str, subtitle: str = "") -> None:
        c = self.c
        print()
        print(f"{c.cyan}{'═' * self.width}{c.reset}")
        print(f"{c.bold}{c.cyan}  {title}{c.reset}")
        if subtitle:
            for ln in wrap_paragraphs(subtitle, self.width - 2):
                print(f"{c.grey}  {ln}{c.reset}")
        print(f"{c.cyan}{'─' * self.width}{c.reset}")

    def info(self, msg: str) -> None:
        print(f"{self.c.grey}{msg}{self.c.reset}")

    def warn(self, msg: str) -> None:
        print(f"{self.c.yellow}! {msg}{self.c.reset}")

    def ok(self, msg: str) -> None:
        print(f"{self.c.green}✓{self.c.reset} {msg}")

    def block(self, text: str) -> None:
        """Print a pre-rendered multi-line block (e.g. the tree) as-is."""
        print(text)

    def replay(self, node, breadcrumb: str) -> None:
        """Re-print a saved node's conversation."""
        self.section(f"[{node.id}] {node.label}", breadcrumb)
        if node.focus:
            print(f"{self.c.grey}  Re-investigating: {node.focus}{self.c.reset}")
        for t in node.turns:
            self.learner(t["turn"], t.get("thinking", ""), t.get("new_term", ""),
                         t.get("action", ""), t.get("confidence"))
            if t.get("tutor"):
                self.tutor(t["tutor"])


class SilentRenderer(Renderer):
    """A Renderer that prints nothing — for investigations running in parallel,
    whose conversations are replayed once they finish (live output from several
    conversations at once would interleave)."""

    def status(self, msg: str) -> None:
        pass

    def clear_status(self) -> None:
        pass

    def learner(self, *args, **kwargs) -> None:
        pass

    def tutor(self, *args, **kwargs) -> None:
        pass
