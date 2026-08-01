"""The knowledge tree: a branchable, persistable forest of investigations.

A :class:`KnowledgeTree` is one portable file (`<topic>.know.json`) describing a
root investigation and every re-investigation branched off it. Nodes are stored
flat (id -> node) with parent/child links, so the (deliberately unbalanced) tree
is easy to serialise, navigate, and merge by copying files around.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from .render import space_sentences

FORMAT = "learn-with-claude/knowledge-tree"
VERSION = 1

# A no-colour palette so rendering works without importing the terminal layer.
_PLAIN = SimpleNamespace(
    reset="", bold="", dim="", grey="", cyan="", green="", blue="", yellow="", magenta=""
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return (s or "topic")[:50]


def one_line(text: str, limit: int = 200) -> str:
    """Collapse a (possibly multi-line) string to a single truncated line."""
    s = re.sub(r"\s+", " ", (text or "").strip())
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def fmt_conf(value) -> str:
    return f"{value}%" if isinstance(value, int) else "—"


def apply_asides(text: str, asides: list, wrap=None) -> str:
    """Splice the reader's own words into a passage, in brackets, after the
    phrase each one annotates — the same place the app shows them.

    Matches across whitespace (the stored anchor is collapsed to single
    spaces, the tutor's prose is not) and only the first occurrence, exactly
    like the browser does, so a re-export never drifts from what was on
    screen. `wrap` lets the HTML export mark its insertions up; the default
    is the plain " (words)" the markdown export wants.
    """
    if not asides:
        return text
    for a in asides:
        words = str(a.get("words") or "").strip()
        anchor = str(a.get("text") or "").strip()
        if not words or not anchor:
            continue
        pattern = r"\s+".join(re.escape(w) for w in anchor.split())
        try:
            match = re.search(pattern, text)
        except re.error:
            continue
        if not match:
            continue
        insert = wrap(words) if wrap else f" ({words})"
        text = text[: match.end()] + insert + text[match.end():]
    return text


def conversation_digest(turns: list, upto: int | None = None) -> str:
    """Compact 'you asked / tutor answered' recap of a conversation, used to seed
    branches with the context the learner already has."""
    lines = []
    for t in turns[:upto]:
        if t.get("action"):
            lines.append(f"  Q: {one_line(t['action'], 160)}")
        if t.get("tutor"):
            lines.append(f"  A: {one_line(t['tutor'], 240)}")
    return "\n".join(lines) or "  (nothing yet)"


# --------------------------------------------------------------------------- #
# Node
# --------------------------------------------------------------------------- #
@dataclass
class Node:
    id: int
    label: str
    parent_id: "int | None" = None
    branch_from_turn: "int | None" = None
    focus: str = ""
    turns: list = field(default_factory=list)
    children: list = field(default_factory=list)
    created: str = ""
    learner_model: str = "sonnet"
    tutor_model: str = "sonnet"
    cost: float = 0.0
    final_confidence: object = None
    learner_level: str = ""
    # for a tutor-chosen follow-up: its one-sentence "why this is the best
    # next step" — display metadata that must survive the web↔CLI round-trip
    why: str = ""

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


_NODE_FIELDS = {f.name for f in fields(Node)}

# top-level keys from_dict/to_dict handle themselves; anything else is an extra
_TREE_KEYS = {"format", "version", "id", "root_topic", "created", "root_id",
              "next", "nodes", "glossary", "note", "highlights"}


# --------------------------------------------------------------------------- #
# Tree
# --------------------------------------------------------------------------- #
class KnowledgeTree:
    def __init__(self, root_topic: str, *, id: str | None = None, created: str | None = None,
                 path: "str | Path | None" = None) -> None:
        self.root_topic = root_topic
        self.id = id or uuid.uuid4().hex[:12]
        self.created = created or _now()
        self.nodes: dict[int, Node] = {}
        self.root_id: int | None = None
        self._next = 1
        self.path: Path | None = Path(path) if path else None
        # term (lowercased key) -> {"term", "def", "node", "turn"}: the words
        # the reader deliberately added in the web app (nothing lands here on
        # its own), each with the definition they asked for, if any
        self.glossary: dict = {}
        # the learner's own free-text synthesis of the tree (optional)
        self.note: str = ""
        # passages the reader marked in the web app: {"node", "turn", "text"}
        self.highlights: list = []
        # top-level keys this version doesn't know (quiz, profile, survey, …)
        # — kept verbatim so a CLI save never strips what the web app stored
        self.extras: dict = {}

    # --- mutation --------------------------------------------------------
    def _alloc(self) -> int:
        i = self._next
        self._next += 1
        return i

    def add_root(self, label, result, *, learner_model="sonnet", tutor_model="sonnet",
                 learner_level="") -> Node:
        node = Node(
            id=self._alloc(), label=label, created=_now(), turns=result.turns,
            cost=result.cost, final_confidence=result.final_confidence,
            learner_model=learner_model, tutor_model=tutor_model,
            learner_level=learner_level,
        )
        self.nodes[node.id] = node
        self.root_id = node.id
        return node

    def add_branch(self, parent_id, branch_turn, focus, label, result,
                   *, learner_model="sonnet", tutor_model="sonnet", learner_level="") -> Node:
        parent = self.nodes[int(parent_id)]
        node = Node(
            id=self._alloc(), label=label, parent_id=parent.id, branch_from_turn=int(branch_turn),
            focus=focus, created=_now(), turns=result.turns, cost=result.cost,
            final_confidence=result.final_confidence,
            learner_model=learner_model, tutor_model=tutor_model,
            learner_level=learner_level,
        )
        self.nodes[node.id] = node
        parent.children.append(node.id)
        return node

    # --- navigation ------------------------------------------------------
    def get(self, node_id) -> "Node | None":
        try:
            return self.nodes.get(int(node_id))
        except (TypeError, ValueError):
            return None

    def lineage(self, node_id) -> list:
        """Nodes from root down to node_id (inclusive)."""
        chain, cur = [], self.get(node_id)
        while cur is not None:
            chain.append(cur)
            cur = self.get(cur.parent_id) if cur.parent_id is not None else None
        return list(reversed(chain))

    def breadcrumb(self, node_id) -> str:
        return " › ".join(n.label for n in self.lineage(node_id)) or self.root_topic

    def total_cost(self) -> float:
        return sum(n.cost for n in self.nodes.values())

    def highlight_map(self) -> dict:
        """(node_id, turn) -> [passage, …] for every well-formed highlight."""
        m: dict = {}
        for h in self.highlights:
            try:
                key = (int(h.get("node")), int(h.get("turn")))
            except (TypeError, ValueError):
                continue
            text = one_line(str(h.get("text") or ""), 300)
            if text:
                m.setdefault(key, []).append(text)
        return m

    def aside_map(self) -> dict:
        """(node_id, turn) -> [{text, words}, …]: the reader's own words,
        written in the web app's 🏷 my words and shown inline in brackets.

        Unlike a highlight, which an export can render beside the turn, an
        aside only means anything *in place* — "mitochondria (power house of
        the cell)". So both exports splice it into the sentence rather than
        listing it underneath; see apply_asides().
        """
        m: dict = {}
        for a in (self.extras.get("asides") or []):
            if not isinstance(a, dict):
                continue
            text = " ".join(str(a.get("text") or "").split())
            words = " ".join(str(a.get("words") or "").split())
            if not text or not words:
                continue
            try:
                key = (int(a.get("node")), int(a.get("turn")))
            except (TypeError, ValueError):
                continue
            if key[0] in self.nodes:
                m.setdefault(key, []).append({"text": text, "words": words})
        return m

    def fact_groups(self) -> list:
        """The ⚡ fact-me-out landscape as [(group name, [fact, …]), …].

        Lives in extras['facts'] (written by the web app). Unlike a
        conversation this is reference material, so it heads both exports as
        its own section rather than being threaded through the turns.
        """
        facts = self.extras.get("facts")
        if not isinstance(facts, dict):
            return []
        out = []
        for group in (facts.get("groups") or []):
            if not isinstance(group, dict):
                continue
            name = str(group.get("name") or "").strip()
            items = [f for f in (group.get("facts") or [])
                     if isinstance(f, dict) and str(f.get("text") or "").strip()]
            if name and items:
                out.append((name, items))
        return out

    def image_map(self) -> dict:
        """(node_id, turn) -> [figure, …] for every generated figure.

        Figures live in extras['images'] (written by the web app's 🖼
        illustrate). Only the *description* travels in the .know.json — the
        pixels are held out of band, since a tree is a text document people
        read and copy between machines. So a CLI reader gets the caption and
        the alt text, which is the part that carries meaning anyway; the web
        app and the HTML export put the picture back.
        """
        m: dict = {}
        for img in (self.extras.get("images") or []):
            if not isinstance(img, dict) or not str(img.get("id") or "").strip():
                continue
            try:
                key = (int(img.get("node")), int(img.get("turn")))
            except (TypeError, ValueError):
                continue
            if key[0] in self.nodes:
                m.setdefault(key, []).append(img)
        for lst in m.values():
            lst.sort(key=lambda i: str(i.get("when") or ""))
        return m

    TEACH_TAGS = {"clean": "✓ clean", "close": "≈ close", "gappy": "△ gappy"}

    def teach_map(self) -> dict:
        """node_id -> teach-back attempts (oldest first). Attempts live in
        extras['teach'] (written by the web app's explain-it-back); ones
        whose node was pruned are skipped, matching the app."""
        out: dict = {}
        for a in (self.extras.get("teach") or []):
            if not isinstance(a, dict) or not str(a.get("text") or "").strip():
                continue
            try:
                nid = int(a.get("node"))
            except (TypeError, ValueError):
                continue
            if nid in self.nodes:
                out.setdefault(nid, []).append(a)
        for lst in out.values():
            lst.sort(key=lambda a: str(a.get("when") or ""))
        return out

    def exam_map(self) -> dict:
        """node_id -> MARKED written exams (oldest first). Papers live in
        extras['exams'] (written by the web app's ✍ exam). A paper that has
        been set but not yet submitted has no marks on it and is work in
        progress, not a record of anything, so it never reaches an export."""
        out: dict = {}
        for e in (self.extras.get("exams") or []):
            if not isinstance(e, dict) or not e.get("submitted"):
                continue
            if not isinstance(e.get("questions"), list) or not isinstance(e.get("results"), list):
                continue
            try:
                nid = int(e.get("node"))
            except (TypeError, ValueError):
                continue
            if nid in self.nodes:
                out.setdefault(nid, []).append(e)
        for lst in out.values():
            lst.sort(key=lambda e: str(e.get("submitted") or ""))
        return out

    @staticmethod
    def exam_rows(exam: dict) -> list:
        """An exam flattened for display: (question, answer, result) triples,
        skipping anything the two lists don't line up on."""
        questions = exam.get("questions") or []
        answers = exam.get("answers") or []
        results = exam.get("results") or []
        rows = []
        for i, q in enumerate(questions):
            if not isinstance(q, dict) or not str(q.get("q") or "").strip():
                continue
            answer = answers[i] if i < len(answers) and isinstance(answers[i], str) else ""
            result = results[i] if i < len(results) and isinstance(results[i], dict) else {}
            rows.append((q, answer, result))
        return rows

    # --- persistence -----------------------------------------------------
    def to_dict(self) -> dict:
        d = {
            "format": FORMAT,
            "version": VERSION,
            "id": self.id,
            "root_topic": self.root_topic,
            "created": self.created,
            "root_id": self.root_id,
            "next": self._next,
            "nodes": {str(nid): asdict(node) for nid, node in self.nodes.items()},
        }
        if self.glossary:
            d["glossary"] = self.glossary
        if self.note:
            d["note"] = self.note
        if self.highlights:
            d["highlights"] = self.highlights
        for k, v in self.extras.items():   # setdefault: an extra never shadows
            d.setdefault(k, v)             # a key this version owns
        return d

    @classmethod
    def from_dict(cls, d: dict, path=None) -> "KnowledgeTree":
        tree = cls(d["root_topic"], id=d.get("id"), created=d.get("created"), path=path)
        tree.root_id = d.get("root_id")
        # tolerate node keys this version doesn't know (trees travel between
        # the web app and the CLI, which don't always ship the same fields)
        tree.nodes = {
            int(k): Node(**{kk: vv for kk, vv in v.items() if kk in _NODE_FIELDS})
            for k, v in d.get("nodes", {}).items()
        }
        tree._next = d.get("next") or (max(tree.nodes, default=0) + 1)
        tree.glossary = d.get("glossary") if isinstance(d.get("glossary"), dict) else {}
        tree.note = d.get("note") if isinstance(d.get("note"), str) else ""
        hl = d.get("highlights")
        tree.highlights = [h for h in hl if isinstance(h, dict)] if isinstance(hl, list) else []
        tree.extras = {k: v for k, v in d.items() if k not in _TREE_KEYS}
        return tree

    def save(self, path=None) -> Path:
        if path is not None:
            self.path = Path(path)
        if self.path is None:
            raise ValueError("no path set for this knowledge tree")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return self.path

    @classmethod
    def load(cls, path) -> "KnowledgeTree":
        path = Path(path)
        d = json.loads(path.read_text(encoding="utf-8"))
        if d.get("format") != FORMAT:
            raise ValueError(f"{path.name} is not a {FORMAT} file")
        return cls.from_dict(d, path=path)

    def default_filename(self) -> str:
        return f"{slug(self.root_topic)}.know.json"

    # --- rendering -------------------------------------------------------
    def render(self, c=None) -> str:
        c = c or _PLAIN
        lines: list[str] = []

        def walk(nid: int, prefix: str, is_last: bool, is_root: bool) -> None:
            node = self.nodes[nid]
            meta = (
                f"{len(node.turns)} turns · conf {fmt_conf(node.final_confidence)}"
                if is_root
                else f"↳T{node.branch_from_turn} · {len(node.turns)} turns · "
                f"conf {fmt_conf(node.final_confidence)}"
            )
            if is_root:
                head = f"{c.bold}● [{node.id}] {node.label}{c.reset}"
                lines.append(f"{head}  {c.grey}({meta}){c.reset}")
                child_prefix = ""
            else:
                connector = "└─ " if is_last else "├─ "
                head = f"{c.bold}● [{node.id}] {node.label}{c.reset}"
                lines.append(f"{prefix}{connector}{head}  {c.grey}({meta}){c.reset}")
                child_prefix = prefix + ("   " if is_last else "│  ")
            kids = node.children
            for i, ch in enumerate(kids):
                walk(ch, child_prefix, i == len(kids) - 1, False)

        if self.root_id is not None:
            walk(self.root_id, "", True, True)
        return "\n".join(lines)

    # --- markdown export -------------------------------------------------
    def to_markdown(self) -> str:
        out = [
            f"# Knowledge tree: {self.root_topic}",
            "",
            f"- created: {self.created}",
            f"- nodes: {len(self.nodes)}  ·  total cost: ${self.total_cost():.4f}",
            "",
        ]
        source = str(self.extras.get("source") or "").strip()
        if source:
            out += ["## Source material", "", "> " + source.replace("\n", "\n> "), "", "---", ""]
        note = (self.note or "").strip()
        if note:
            out += ["## My notes", "", note, "", "---", ""]
        facts = self.fact_groups()
        if facts:
            out += ["## The landscape", ""]
            for name, items in facts:
                out += [f"### {name}", ""]
                for f in items:
                    kind = str(f.get("kind") or "").strip()
                    tag = f"*({kind})* " if kind else ""
                    out.append(f"- {tag}{one_line(str(f['text']), 300)}")
                out.append("")
            out += ["---", ""]
        out += [
            "## Map",
            "",
            "```",
            self.render(),
            "```",
            "",
            "---",
            "",
        ]

        hl_map = self.highlight_map()
        img_map = self.image_map()
        aside_map = self.aside_map()

        def walk(nid: int, depth: int) -> None:
            node = self.nodes[nid]
            hashes = "#" * min(6, depth + 2)
            if node.is_root:
                out.append(f"{hashes} [{node.id}] {node.label}")
            else:
                out.append(
                    f"{hashes} [{node.id}] {node.label}  "
                    f"(↳ from turn {node.branch_from_turn} of node [{node.parent_id}])"
                )
            out.append("")
            if node.focus:
                out.append(f"**Re-investigating:** {node.focus}")
                out.append("")
            for t in node.turns:
                conf = f" · confidence {t['confidence']}%" if t.get("confidence") is not None else ""
                out.append(f"**Turn {t['turn']}{conf}**")
                out.append("")
                if t.get("thinking"):
                    out.append(f"> 💭 Thinking to myself: {t['thinking']}")
                    out.append("")
                if t.get("new_term"):
                    out.append(f"> 🔍 New word I hit: {t['new_term']}")
                    out.append("")
                if t.get("quote"):
                    # a question asked about a specific passage keeps it
                    out.append(f"> ❝ About: {one_line(t['quote'], 400)}")
                    out.append("")
                out.append(f"🙋 **I ask Claude:** {t['action']}")
                out.append("")
                if t.get("tutor"):
                    answer = apply_asides(space_sentences(t["tutor"]),
                                          aside_map.get((node.id, t.get("turn"))))
                    out.append(f"📘 **Claude answers:** {answer}")
                    out.append("")
                for passage in hl_map.get((node.id, t.get("turn")), []):
                    out.append(f"> ★ I highlighted: {passage}")
                    out.append("")
                # The picture itself can't come along — markdown would have to
                # carry it as a multi-hundred-KB data URI per figure, which
                # would make the export unreadable in the editors people
                # actually open .md files in. The description does travel, and
                # `export html` embeds the real thing.
                for fig in img_map.get((node.id, t.get("turn")), []):
                    caption = one_line(str(fig.get("caption") or "a figure"), 120)
                    out.append(f"> 🖼 **Figure — {caption}**")
                    alt = one_line(str(fig.get("alt") or ""), 400)
                    if alt:
                        out.append(">")
                        out.append(f"> {alt}")
                    out.append("")
            out.append("---")
            out.append("")
            for ch in node.children:
                walk(ch, depth + 1)

        if self.root_id is not None:
            walk(self.root_id, 0)

        defined = sorted(
            (e for e in self.glossary.values() if isinstance(e, dict) and e.get("def")),
            key=lambda e: str(e.get("term", "")).lower(),
        )
        if defined:
            out.append("## Glossary")
            out.append("")
            for e in defined:
                reason = str(e.get("reason") or "").strip()
                label = f"{e['term']} ({reason})" if reason and reason != "definition" else e["term"]
                out.append(f"- **{label}** — {e['def']}")
            out.append("")

        teach = self.teach_map()
        if teach:
            out.append("## Explained back")
            out.append("")
            for nid in sorted(teach):
                last = teach[nid][-1]
                verdict = str(last.get("verdict") or "").strip()
                tag = self.TEACH_TAGS.get(verdict, "")
                n = len(teach[nid])
                out.append(f"**[{nid}] {self.nodes[nid].label}**"
                           + (f" — {tag}" if tag else "")
                           + (f" (attempt {n})" if n > 1 else ""))
                out.append("")
                out.append(f"> 🗣 {last['text']}")
                out.append("")
                missing = str(last.get("missing") or "").strip()
                if verdict != "clean" and missing:
                    out.append(f"The gap that mattered: {missing}")
                    out.append("")

        exams = self.exam_map()
        if exams:
            out.append("## Exams")
            out.append("")
            for nid in sorted(exams):
                for exam in exams[nid]:
                    total, mx = exam.get("total"), exam.get("max")
                    score = f" — {total}/{mx}" if isinstance(total, int) and mx else ""
                    sat = str(exam.get("submitted") or "")[:10]
                    out.append(f"### [{nid}] {self.nodes[nid].label}{score}"
                               + (f"  ({sat})" if sat else ""))
                    out.append("")
                    overall = str(exam.get("overall") or "").strip()
                    if overall:
                        out.append(f"> {overall.replace(chr(10), ' ')}")
                        out.append("")
                    for i, (q, answer, result) in enumerate(self.exam_rows(exam), 1):
                        marks = result.get("marks")
                        got = f" — {marks}/{q.get('marks', 10)}" if isinstance(marks, int) else ""
                        out.append(f"**Q{i}{got}.** {q['q']}")
                        out.append("")
                        out.append("> ✍ " + (answer.strip().replace("\n", "\n> ")
                                             if answer.strip() else "(left blank)"))
                        out.append("")
                        for label, key in (("What you earned", "earned"),
                                           ("What would have earned more", "improve")):
                            text = str(result.get(key) or "").strip()
                            if text:
                                out.append(f"*{label}:* {text}")
                                out.append("")
                    out.append("---")
                    out.append("")
        return "\n".join(out)
