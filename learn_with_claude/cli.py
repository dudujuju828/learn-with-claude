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
from .personas import TUTOR_WORDS_DEFAULT, TUTOR_WORDS_MAX, TUTOR_WORDS_MIN
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
    p.add_argument("-m", "--model", default="claude-sonnet-5",
                   help="Model for both personas (default: claude-sonnet-5).")
    p.add_argument("--learner-model", default=None, help="Override the learner's model.")
    p.add_argument("--tutor-model", default=None, help="Override the tutor's model.")
    p.add_argument("--effort", default="xhigh",
                   choices=["low", "medium", "high", "xhigh", "max"],
                   help="Reasoning effort for both personas (default: xhigh).")
    p.add_argument("--level", default="student",
                   choices=["novice", "student", "practitioner", "expert"],
                   help="How much the simulated learner already knows — shapes the "
                        "questions it can ask (default: student).")
    p.add_argument("--double-check", action="store_true",
                   help="Read every tutor answer back before it is shown — for wrong "
                        "claims, misleading wording, and the rules it was given. "
                        "Corrections are printed and saved with what it said first. "
                        "Costs a third model call per turn.")
    p.add_argument("--answer-words", type=int, default=TUTOR_WORDS_DEFAULT,
                   metavar="N",
                   help=f"How long one tutor answer must be, in words — a "
                        f"floor, not a cap: an answer that lands under it is "
                        f"unfinished (default: {TUTOR_WORDS_DEFAULT}, clamped "
                        f"to {TUTOR_WORDS_MIN}-{TUTOR_WORDS_MAX}). The tutor is "
                        "told to reach it by going deeper into the same "
                        "question, never by padding, and to come up short "
                        "rather than invent. The web app sets this under "
                        "'answer length'.")
    p.add_argument("--code", nargs="?", const="", default=None, metavar="LANGUAGE",
                   help="Ground answers in real code: short snippets with the "
                        "actual function and type names, rather than prose about "
                        "what the code would look like. Give a language to pin "
                        "them to it (--code python); omit it and the tutor picks "
                        "whatever the question implies.")
    p.add_argument("-d", "--dir", default=None,
                   help=f"Knowledge directory (default: $LEARN_DIR or {DEFAULT_DIR}).")
    p.add_argument("--width", type=int, default=66,
                   help="Terminal wrap width for readability (default: 66, dyslexia-friendly).")
    p.add_argument("--line-spacing", type=int, default=1, choices=[1, 2],
                   help="1 = single, 2 = extra blank line between lines.")
    p.add_argument("--timeout", type=int, default=300, help="Per-call timeout in seconds.")
    p.add_argument("--once", action="store_true", help="With a topic: create the tree and exit (no shell).")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI colour output.")
    p.add_argument("--web", action="store_true",
                   help="Serve the web app on localhost, backed by your GitHub "
                        "Copilot login (no API key). Honours --dir; see also --port.")
    p.add_argument("--port", type=int, default=8577,
                   help="Port for --web (default: 8577).")
    p.add_argument("--no-open", action="store_true",
                   help="With --web: don't open the browser.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    prepare_console()

    if args.web:
        from .localweb import serve

        return serve(port=args.port, knowledge_dir=args.dir,
                     open_browser=not args.no_open)

    shell = Shell(
        knowledge_dir=args.dir or DEFAULT_DIR,
        color=not args.no_color,
        max_turns=args.max_turns,
        learner_model=args.learner_model or args.model,
        tutor_model=args.tutor_model or args.model,
        effort=args.effort,
        level=args.level,
        double_check=args.double_check,
        answer_words=args.answer_words,
        # --code with no value means "yes, any language"; absent means off
        code=args.code is not None,
        code_language=args.code or "",
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
