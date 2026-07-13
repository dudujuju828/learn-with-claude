"""Plain-python regression tests for the web app's server-side helpers.

Run with:  python tests/test_web_helpers.py
(no test framework needed — asserts throughout, prints ok per group)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.index import split_tutor_parts  # noqa: E402
from learn_with_claude.export_html import tree_to_html  # noqa: E402
from learn_with_claude.knowledge import KnowledgeTree  # noqa: E402
from learn_with_claude.personas import (  # noqa: E402
    LEARNER_LEVELS,
    LEARNER_SYSTEM,
    define_message,
    learner_system,
    quiz_message,
    tutor_system,
)


def test_learner_levels():
    assert set(LEARNER_LEVELS) == {"novice", "student", "practitioner", "expert"}
    assert learner_system("student") == LEARNER_SYSTEM
    assert learner_system("unknown") == LEARNER_SYSTEM  # bad level falls back
    for lv in LEARNER_LEVELS:
        s = learner_system(lv)
        assert "OUTPUT CONTRACT" in s and "HUMAN LEARNER" in s
        # the level addendum lands between the persona and the contract
        assert s.index("WHO YOU ARE") < s.index("OUTPUT CONTRACT")
    assert "YOUR LEVEL — EXPERT" in learner_system("expert")
    print("ok  learner levels")


def test_tutor_system_segments():
    base = tutor_system(diagrams=False)
    assert "MARKUP" not in base  # the CLI stays plain
    seg = tutor_system(diagrams=False, segments=True)
    assert "MARKUP" in seg and "[watch out]" in seg
    print("ok  tutor segments flag")


def test_split_tutor_parts():
    # no markup -> no parts
    assert split_tutor_parts("One idea.\n\nTwo ideas.") == []
    # numeric citation brackets are not tags
    assert split_tutor_parts("See refs.\n[1] a\n[2] b") == []
    # tags split; code fences are opaque
    text = (
        "Direct answer.\n\n[why]\nBecause of X.\n\n[example]\n"
        "```\n[not a tag]\ncode()\n```\n\n[watch out]\nEdge case."
    )
    parts = split_tutor_parts(text)
    assert [p["label"] for p in parts] == ["", "why", "example", "watch out"]
    assert "[not a tag]" in parts[2]["text"]
    # tag with trailing text on the same line
    parts = split_tutor_parts("Answer.\n[why] reason here.")
    assert parts[1] == {"label": "why", "text": "reason here."}
    print("ok  tutor part parser")


def test_knowledge_round_trip():
    d = {
        "format": "learn-with-claude/knowledge-tree", "version": 1, "id": "t1",
        "root_topic": "x", "created": "2026-07-13", "root_id": 1, "next": 2,
        "nodes": {"1": {
            "id": 1, "label": "x", "children": [],
            "turns": [{"turn": 1, "action": "q", "tutor": "a", "new_term": "widget",
                       "confidence": 40,
                       "parts": [{"label": "", "text": "a"}]}],
            "learner_level": "expert",
            "unknown_future_field": {"nested": True},   # must not crash
        }},
        "glossary": {"widget": {"term": "widget", "def": "A thing.", "node": 1, "turn": 1}},
        "quiz": {"made": "2026-07-13", "questions": []},   # unknown top-level key
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.nodes[1].learner_level == "expert"
    assert kb.glossary["widget"]["def"] == "A thing."
    out = kb.to_dict()
    assert out["glossary"]["widget"]["term"] == "widget"
    assert out["nodes"]["1"]["turns"][0]["parts"][0]["text"] == "a"  # turn extras survive
    md = kb.to_markdown()
    assert "## Glossary" in md and "**widget** — A thing." in md
    html = tree_to_html(kb)
    assert "Glossary" in html and "A thing." in html
    print("ok  knowledge round-trip (glossary, levels, unknown keys)")


def test_message_builders():
    m = define_message("load factor", "hash tables", "A: it is a ratio.")
    assert "load factor" in m and "hash tables" in m
    q = quiz_message("hash tables", "Q: what\nA: this", 5)
    assert "5 questions" in q
    print("ok  message builders")


if __name__ == "__main__":
    test_learner_levels()
    test_tutor_system_segments()
    test_split_tutor_parts()
    test_knowledge_round_trip()
    test_message_builders()
    print("\nall green")
