"""Interactive knowledge shell — a claude-code-style terminal for growing,
branching, and importing trees of knowledge."""

from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .backend import ClaudeError
from .knowledge import KnowledgeTree, conversation_digest, one_line, slug
from .personas import (
    branch_learner_message,
    branch_tutor_context,
    followup_learner_message,
    followup_tutor_context,
)
from .render import Renderer, SilentRenderer
from .simulator import pick_next_concept, run_conversation

# A `full` session = the root investigation + this many tutor-chosen follow-ups.
FULL_FOLLOWUPS = 3

# How many `many` investigations run at the same time.
MANY_WORKERS = 4

HELP = """\
commands:
  new <topic>              start a new knowledge tree (runs the root investigation)
  full <topic>             like 'new', then the tutor reviews the conversation and
                           picks the next best related concept to explore — repeated
                           so the tree ends up with 4 linked investigations
  many "<q1>", "<q2>", ... run one 'new' investigation per quoted question, all in
                           parallel; each conversation replays as it finishes and
                           is saved as its own tree
  branch <node> <turn> [focus]
                           re-investigate node's tutor answer at <turn>, going deeper.
                           optional [focus] steers what to dig into; else the learner picks.
  tree                     show the current tree
  show <node>              replay a node's full conversation
  open <file|index>        load a knowledge tree from the knowledge dir
  list                     list knowledge trees in the knowledge dir
  import <path>            copy an external .know.json into the knowledge dir and open it
  export [md|html] [file]  write the tree to readable markdown, or a dyslexia-friendly
                           HTML page (selectable font, size, line spacing)
  seeplusplus <file> [out] export a C++ source file to the same dyslexia-friendly
                           HTML, one row per line, arrow-key line stepper included
  save [file]              save the current tree (auto-saves after new/branch)
  cost                     show total spend on the current tree
  help                     show this help
  quit / exit              leave
"""


class Shell:
    def __init__(self, knowledge_dir="knowledge", *, color=True, max_turns=20,
                 learner_model="claude-sonnet-5", tutor_model="claude-sonnet-5",
                 effort="xhigh", level="student", timeout=300,
                 double_check=False, width=66, line_spacing=1) -> None:
        self.dir = Path(knowledge_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.r = Renderer(color=color, width=width, spacing=line_spacing)
        self.max_turns = max_turns
        self.learner_model = learner_model
        self.tutor_model = tutor_model
        self.effort = effort
        self.level = level
        self.timeout = timeout
        self.double_check = double_check
        self.kb: KnowledgeTree | None = None

    # ------------------------------------------------------------------ #
    # main loop
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self.r.shell_banner(self.dir)
        self.cmd_list("")
        while True:
            try:
                line = input(self._prompt()).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not line:
                continue
            if not self._dispatch(line):
                break
        self.r.info("bye.")

    def _prompt(self) -> str:
        c = self.r.c
        name = one_line(self.kb.root_topic, 30) if self.kb else "no tree"
        return f"\n{c.bold}{c.cyan}learn{c.reset} {c.grey}({name}){c.reset} › "

    def _dispatch(self, line: str) -> bool:
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        handlers = {
            "new": self.cmd_new, "learn": self.cmd_new,
            "full": self.cmd_full, "many": self.cmd_many,
            "branch": self.cmd_branch, "dig": self.cmd_branch,
            "tree": self.cmd_tree, "show": self.cmd_show,
            "open": self.cmd_open, "list": self.cmd_list, "ls": self.cmd_list,
            "import": self.cmd_import, "export": self.cmd_export,
            "seeplusplus": self.cmd_seeplusplus, "spp": self.cmd_seeplusplus,
            "save": self.cmd_save, "cost": self.cmd_cost,
            "help": self.cmd_help, "?": self.cmd_help,
        }
        if cmd in ("quit", "exit", "q"):
            return False
        handler = handlers.get(cmd)
        if handler is None:
            self.r.warn(f"unknown command: {cmd!r}  (type 'help')")
            return True
        try:
            handler(arg)
        except ClaudeError as exc:
            self.r.warn(f"claude error: {exc}")
        return True

    # ------------------------------------------------------------------ #
    # commands
    # ------------------------------------------------------------------ #
    def cmd_help(self, arg: str) -> None:
        print(HELP)

    def cmd_new(self, topic: str) -> None:
        topic = topic.strip()
        if not topic:
            self.r.warn("usage: new <topic>")
            return
        kb = KnowledgeTree(topic, path=self._unique_path(topic))
        self.r.section(f"new tree: {topic}", f"learner={self.learner_model} tutor={self.tutor_model}")
        result = run_conversation(
            topic, max_turns=self.max_turns, learner_model=self.learner_model,
            tutor_model=self.tutor_model, effort=self.effort, level=self.level,
            timeout=self.timeout, double_check=self.double_check, renderer=self.r,
        )
        kb.add_root(topic, result, learner_model=self.learner_model, tutor_model=self.tutor_model,
                    learner_level=self.level)
        kb.save()
        self.kb = kb
        self.r.ok(f"saved → {kb.path}")
        self._print_tree()

    def cmd_many(self, arg: str) -> None:
        topics = re.findall(r'"([^"]+)"', arg)
        if not topics:  # tolerate unquoted, comma-separated questions
            topics = [t.strip() for t in arg.split(",") if t.strip()]
        if not topics:
            self.r.warn('usage: many "question one", "question two", ...')
            return
        if len(topics) == 1:
            self.cmd_new(topics[0])
            return

        self.r.section(f"many: {len(topics)} investigations in parallel",
                       f"learner={self.learner_model} tutor={self.tutor_model}")
        for i, t in enumerate(topics, 1):
            self.r.info(f"  {i}. {t}")

        silent = SilentRenderer()

        def worker(topic: str):
            return run_conversation(
                topic, max_turns=self.max_turns, learner_model=self.learner_model,
                tutor_model=self.tutor_model, effort=self.effort, level=self.level,
                timeout=self.timeout, double_check=self.double_check, renderer=silent,
            )

        trees: dict[str, KnowledgeTree] = {}
        total, done = len(topics), 0
        with ThreadPoolExecutor(max_workers=min(MANY_WORKERS, total)) as pool:
            futures = {pool.submit(worker, t): t for t in topics}
            self.r.status(f"0/{total} done — investigating in parallel…")
            try:
                for fut in as_completed(futures):
                    topic = futures[fut]
                    done += 1
                    self.r.clear_status()
                    try:
                        result = fut.result()
                    except ClaudeError as exc:
                        self.r.warn(f'"{one_line(topic, 50)}" failed: {exc}')
                    else:
                        kb = KnowledgeTree(topic, path=self._unique_path(topic))
                        node = kb.add_root(topic, result, learner_model=self.learner_model,
                                           tutor_model=self.tutor_model, learner_level=self.level)
                        kb.save()
                        trees[topic] = kb
                        self.r.replay(node, f"finished {done}/{total}")
                        self.r.ok(f"saved → {kb.path}")
                    if done < total:
                        self.r.status(f"{done}/{total} done — still investigating…")
            except KeyboardInterrupt:
                self.r.clear_status()
                self.r.warn("interrupted — queued investigations cancelled; the ones "
                            "already running must finish their conversation first")
                pool.shutdown(cancel_futures=True)

        for t in topics:  # open the first question's tree (in the order given)
            if t in trees:
                self.kb = trees[t]
                break
        self.r.ok(f"many done: {len(trees)}/{total} trees saved"
                  + (f"  ·  open tree: '{one_line(self.kb.root_topic, 40)}'" if trees else ""))
        self.cmd_list("")

    def cmd_full(self, topic: str) -> None:
        topic = topic.strip()
        if not topic:
            self.r.warn("usage: full <topic>")
            return
        self.cmd_new(topic)
        if self.kb is None:
            return
        for _ in range(FULL_FOLLOWUPS):
            if not self._explore_next():
                break
        self.r.ok(f"full session done: {len(self.kb.nodes)} investigations "
                  f"(export html for the map)")

    def _explore_next(self) -> bool:
        """One `full`-session step: the tutor reviews everything covered so far,
        picks the next related concept, and the learner investigates it."""
        kb = self.kb
        order = sorted(kb.nodes)
        covered = [kb.nodes[i].label for i in order]
        recap = "\n".join(
            f"[{kb.nodes[i].label}]\n{conversation_digest(kb.nodes[i].turns)}" for i in order
        )

        self.r.status("tutor is choosing the next concept…")
        pick, pick_cost = pick_next_concept(
            kb.root_topic, covered, recap,
            model=self.tutor_model, effort=self.effort, timeout=self.timeout,
        )
        self.r.clear_status()
        if pick is None:
            self.r.warn("the tutor couldn't pick a next concept — stopping here")
            return False
        concept = one_line(str(pick.get("concept")), 60)
        question = one_line(str(pick.get("opening_question") or ""), 200)
        reason = one_line(str(pick.get("reason") or ""), 120)

        self.r.section(f"next: {concept}", reason)
        if question:
            self.r.info(f'  opening question: "{question}"')
        result = run_conversation(
            concept,
            learner_first_msg=followup_learner_message(kb.root_topic, recap, concept, question),
            anchor=question or concept,
            tutor_extra_system=followup_tutor_context(recap, concept),
            max_turns=self.max_turns, learner_model=self.learner_model,
            tutor_model=self.tutor_model, effort=self.effort, level=self.level,
            timeout=self.timeout, double_check=self.double_check, renderer=self.r,
        )
        result.cost += pick_cost  # the picker call belongs to this node

        prev = kb.nodes[order[-1]]  # chain onto the latest investigation
        node = kb.add_branch(
            prev.id, len(prev.turns) or 1, "", concept, result,
            learner_model=self.learner_model, tutor_model=self.tutor_model,
            learner_level=self.level,
        )
        node.why = reason
        kb.save()
        self.r.ok(f"added node [{node.id}] '{concept}'  →  {kb.path}")
        self._print_tree()
        return True

    def cmd_branch(self, arg: str) -> None:
        if not self._require_kb():
            return
        parts = arg.split(maxsplit=2)
        if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
            self.r.warn("usage: branch <node> <turn> [focus]")
            return
        node_id, branch_turn = int(parts[0]), int(parts[1])
        focus = parts[2].strip() if len(parts) > 2 else ""

        parent = self.kb.get(node_id)
        if parent is None:
            self.r.warn(f"no node [{node_id}] (see 'tree')")
            return
        if not (1 <= branch_turn <= len(parent.turns)):
            self.r.warn(f"node [{node_id}] has turns 1..{len(parent.turns)}")
            return
        bt = parent.turns[branch_turn - 1]
        if not bt.get("tutor"):
            self.r.warn(f"turn {branch_turn} of node [{node_id}] has no tutor answer to dig into")
            return

        breadcrumb = self.kb.breadcrumb(node_id)
        digest = conversation_digest(parent.turns, upto=branch_turn)
        learner_msg = branch_learner_message(
            self.kb.root_topic, breadcrumb, digest, bt["action"], bt["tutor"], focus
        )
        tutor_ctx = branch_tutor_context(digest, bt["tutor"])

        self.r.section(
            f"branch from [{node_id}] turn {branch_turn}",
            f"{breadcrumb}   ·   {('focus: ' + focus) if focus else 'learner-chosen focus'}",
        )
        self.r.info(f'  re-investigating: "{one_line(bt["tutor"], 100)}"')
        result = run_conversation(
            focus or "deeper dive", learner_first_msg=learner_msg, tutor_extra_system=tutor_ctx,
            # No explicit focus means the learner picks its own thread on turn 1,
            # so anchor it to the point being re-investigated rather than to the
            # placeholder topic.
            anchor=focus or f'going deeper on this point: "{one_line(bt["tutor"], 160)}"',
            max_turns=self.max_turns, learner_model=self.learner_model,
            tutor_model=self.tutor_model, effort=self.effort, level=self.level,
            timeout=self.timeout, double_check=self.double_check, renderer=self.r,
        )

        label = focus or self._derive_label(result, bt["tutor"])
        node = self.kb.add_branch(
            node_id, branch_turn, focus, label, result,
            learner_model=self.learner_model, tutor_model=self.tutor_model,
            learner_level=self.level,
        )
        self.kb.save()
        self.r.ok(f"added node [{node.id}] '{label}'  →  {self.kb.path}")
        self._print_tree()

    def cmd_tree(self, arg: str) -> None:
        if self._require_kb():
            self._print_tree()

    def cmd_show(self, arg: str) -> None:
        if not self._require_kb():
            return
        node = self.kb.get(arg.strip())
        if node is None:
            self.r.warn("usage: show <node>  (see 'tree')")
            return
        self.r.replay(node, self.kb.breadcrumb(node.id))

    def cmd_open(self, arg: str) -> None:
        arg = arg.strip()
        files = self._kb_files()
        path = None
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(files):
                path = files[idx]
        else:
            cand = self.dir / arg
            for p in (cand, cand.with_suffix(".json"), self.dir / f"{arg}.know.json"):
                if p.exists():
                    path = p
                    break
        if path is None:
            self.r.warn(f"no such tree: {arg!r}  (try 'list')")
            return
        self.kb = KnowledgeTree.load(path)
        self.r.ok(f"opened {path.name}")
        self._print_tree()

    def cmd_list(self, arg: str) -> None:
        files = self._kb_files()
        if not files:
            self.r.info("no knowledge trees yet — try: new <topic>")
            return
        c = self.r.c
        print(f"{c.grey}knowledge trees in {self.dir}:{c.reset}")
        for i, p in enumerate(files, 1):
            topic, n = self._peek(p)
            print(f"  {c.bold}{i}{c.reset}  {topic}  {c.grey}({n} nodes · {p.name}){c.reset}")

    def cmd_import(self, arg: str) -> None:
        src = Path(arg.strip())
        if not src.is_file():
            self.r.warn(f"no such file: {src}")
            return
        dest = self.dir / src.name
        shutil.copy2(src, dest)
        self.r.ok(f"imported {src.name} → {dest}")
        try:
            self.kb = KnowledgeTree.load(dest)
            self._print_tree()
        except ValueError as exc:
            self.r.warn(str(exc))

    def cmd_export(self, arg: str) -> None:
        if not self._require_kb():
            return
        tokens = arg.split()
        fmt, rest = None, arg.strip()
        if tokens and tokens[0].lower() in ("md", "markdown", "html"):
            fmt = "html" if tokens[0].lower() == "html" else "md"
            rest = arg.split(maxsplit=1)[1].strip() if len(tokens) > 1 else ""
        path = Path(rest) if rest else None
        if fmt is None:
            fmt = "html" if (path and path.suffix.lower() in (".html", ".htm")) else "md"
        if path is None:
            path = self.dir / f"{slug(self.kb.root_topic)}.{'html' if fmt == 'html' else 'md'}"
        if fmt == "html":
            from .export_html import tree_to_html
            path.write_text(tree_to_html(self.kb), encoding="utf-8")
            self.r.ok(f"exported dyslexia-friendly HTML → {path}")
        else:
            path.write_text(self.kb.to_markdown(), encoding="utf-8")
            self.r.ok(f"exported markdown → {path}")

    def cmd_seeplusplus(self, arg: str) -> None:
        parts = [p.strip('"') for p in re.findall(r'"[^"]+"|\S+', arg)]
        if not parts:
            self.r.warn("usage: seeplusplus <file.cpp> [out.html]")
            return
        src = Path(parts[0])
        if not src.is_file():
            self.r.warn(f"no such file: {src}")
            return
        out = Path(parts[1]) if len(parts) > 1 else self.dir / f"{src.stem}.cpp.html"
        try:
            source = src.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.r.warn(f"could not read {src}: {exc}")
            return
        from .export_code import code_to_html
        out.write_text(code_to_html(src.name, source), encoding="utf-8")
        self.r.ok(f"exported dyslexia-friendly code view → {out}")

    def cmd_save(self, arg: str) -> None:
        if not self._require_kb():
            return
        path = Path(arg.strip()) if arg.strip() else None
        if path and not path.is_absolute() and path.parent == Path("."):
            path = self.dir / path
        self.r.ok(f"saved → {self.kb.save(path)}")

    def cmd_cost(self, arg: str) -> None:
        if self._require_kb():
            self.r.info(f"total spend on this tree: ${self.kb.total_cost():.4f} "
                        f"across {len(self.kb.nodes)} investigations")

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _require_kb(self) -> bool:
        if self.kb is None:
            self.r.warn("no tree open — use 'new <topic>' or 'open <file>'")
            return False
        return True

    def _print_tree(self) -> None:
        print()
        self.r.block(self.kb.render(self.r.c))

    def _kb_files(self) -> list:
        return sorted(self.dir.glob("*.know.json"))

    def _unique_path(self, topic: str) -> Path:
        base = self.dir / f"{slug(topic)}.know.json"
        if not base.exists():
            return base
        i = 2
        while (cand := self.dir / f"{slug(topic)}-{i}.know.json").exists():
            i += 1
        return cand

    @staticmethod
    def _peek(path: Path):
        try:
            import json
            d = json.loads(path.read_text(encoding="utf-8"))
            return d.get("root_topic", path.stem), len(d.get("nodes", {}))
        except Exception:
            return path.stem, "?"

    @staticmethod
    def _derive_label(result, tutor_text: str) -> str:
        for t in result.turns:
            if t.get("new_term"):
                return t["new_term"]
        words = one_line(tutor_text, 60).split()
        return " ".join(words[:5]) + ("…" if len(words) > 5 else "") or "deeper dive"
