"""Command-line entry point.

    learn                       open the interactive knowledge shell
    learn "Python decorators"   start a tree on that topic, then drop into the shell
    learn "..." --once          start the tree and exit (non-interactive)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .backend import ClaudeError
from .render import prepare_console
from .repl import Shell

# A stable per-user home for knowledge trees, so the global `learn` command keeps
# all trees in one place regardless of which directory you launch it from.
# Override with --dir or the LEARN_DIR environment variable.
DEFAULT_DIR = os.environ.get("LEARN_DIR") or str(Path.home() / ".learn-with-claude" / "knowledge")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="learn",
        description="Grow a branchable tree of knowledge by having a simulated human "
        "learner investigate a topic with Claude, one scoped step at a time.",
    )
    p.add_argument("topic", nargs="*", help='Optional topic to start a tree on, e.g. "hash tables".')
    p.add_argument(
        "-n", "--max-turns", type=int, default=20,
        help="Safety cap on exchanges per investigation (default: 20).",
    )
    p.add_argument("-m", "--model", default="sonnet", help="Model for both personas (default: sonnet).")
    p.add_argument("--learner-model", default=None, help="Override the learner's model.")
    p.add_argument("--tutor-model", default=None, help="Override the tutor's model.")
    p.add_argument("-d", "--dir", default=None,
                   help=f"Knowledge directory (default: $LEARN_DIR or {DEFAULT_DIR}).")
    p.add_argument("--width", type=int, default=66,
                   help="Terminal wrap width for readability (default: 66, dyslexia-friendly).")
    p.add_argument("--line-spacing", type=int, default=1, choices=[1, 2],
                   help="1 = single, 2 = extra blank line between lines.")
    p.add_argument("--timeout", type=int, default=300, help="Per-call timeout in seconds.")
    p.add_argument("--once", action="store_true", help="With a topic: create the tree and exit (no shell).")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colour output.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prepare_console()

    shell = Shell(
        knowledge_dir=args.dir or DEFAULT_DIR,
        color=not args.no_color,
        max_turns=args.max_turns,
        learner_model=args.learner_model or args.model,
        tutor_model=args.tutor_model or args.model,
        timeout=args.timeout,
        width=args.width,
        line_spacing=args.line_spacing,
    )

    try:
        topic = " ".join(args.topic).strip()
        if topic:
            shell.cmd_new(topic)
            if not args.once:
                shell.run()
        else:
            shell.run()
    except ClaudeError as exc:
        print(f"\nerror talking to claude: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
