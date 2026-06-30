#!/usr/bin/env python3
"""Grow a branchable tree of knowledge with a simulated human learner + Claude.

    python learn.py                       # open the interactive knowledge shell
    python learn.py "Python decorators"   # start a tree, then drop into the shell
    python learn.py "hash tables" --once  # start a tree and exit

Inside the shell: new / branch / tree / show / open / list / import / export / save.
"""

from learn_with_claude.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
