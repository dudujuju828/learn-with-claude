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

    @property
    def is_root(self) -> bool:
        return self.parent_id is None


_NODE_FIELDS = {f.name for f in fields(Node)}


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
        # term (lowercased key) -> {"term", "def", "node", "turn"}: every word
        # the learner hit, with the definition the web app generated for it
        self.glossary: dict = {}

    # --- mutation --------------------------------------------------------
    def _alloc(self) -> int:
        i = self._next
        self._next += 1
        return i

    def add_root(self, label, result, *, learner_model="sonnet", tutor_model="sonnet") -> Node:
        node = Node(
            id=self._alloc(), label=label, created=_now(), turns=result.turns,
            cost=result.cost, final_confidence=result.final_confidence,
            learner_model=learner_model, tutor_model=tutor_model,
        )
        self.nodes[node.id] = node
        self.root_id = node.id
        return node

    def add_branch(self, parent_id, branch_turn, focus, label, result,
                   *, learner_model="sonnet", tutor_model="sonnet") -> Node:
        parent = self.nodes[int(parent_id)]
        node = Node(
            id=self._alloc(), label=label, parent_id=parent.id, branch_from_turn=int(branch_turn),
            focus=focus, created=_now(), turns=result.turns, cost=result.cost,
            final_confidence=result.final_confidence,
            learner_model=learner_model, tutor_model=tutor_model,
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
            "## Map",
            "",
            "```",
            self.render(),
            "```",
            "",
            "---",
            "",
        ]

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
                out.append(f"🙋 **I ask Claude:** {t['action']}")
                out.append("")
                if t.get("tutor"):
                    out.append(f"📘 **Claude answers:** {space_sentences(t['tutor'])}")
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
                out.append(f"- **{e['term']}** — {e['def']}")
            out.append("")
        return "\n".join(out)
