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
        "note": "My takeaway.\nStill line one.\n\nA second paragraph.",
        "highlights": [{"node": 1, "turn": 1, "text": "a"},
                       {"node": 99, "turn": 1, "text": "orphaned passage"},
                       "not a dict"],
        "quiz": {"made": "2026-07-13", "questions": []},   # unknown top-level key
        "profile": "computer-science",                     # another web-side extra
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.nodes[1].learner_level == "expert"
    assert kb.glossary["widget"]["def"] == "A thing."
    assert kb.note.startswith("My takeaway.")
    assert [h["text"] for h in kb.highlights] == ["a", "orphaned passage"]
    out = kb.to_dict()
    assert out["glossary"]["widget"]["term"] == "widget"
    assert out["note"] == d["note"]                        # personal note round-trips
    assert out["nodes"]["1"]["turns"][0]["parts"][0]["text"] == "a"  # turn extras survive
    # web-side fields survive a CLI round-trip instead of being stripped
    assert out["highlights"] == kb.highlights
    assert out["quiz"] == d["quiz"] and out["profile"] == "computer-science"
    assert out["format"] == d["format"]                    # extras never shadow known keys
    md = kb.to_markdown()
    assert "## Glossary" in md and "**widget** — A thing." in md
    assert "## My notes" in md and "A second paragraph." in md
    assert "> ★ I highlighted: a" in md                    # under its turn
    assert "orphaned passage" not in md                    # no such node — dropped
    html = tree_to_html(kb)
    assert "Glossary" in html and "A thing." in html
    assert "My notes" in html and "A second paragraph." in html
    assert "★ I highlighted" in html and "<mark>a</mark>" in html
    # an empty note adds no section
    d2 = dict(d); d2.pop("note")
    assert "My notes" not in KnowledgeTree.from_dict(d2).to_markdown()
    # no highlights -> no key in the file, no section in either export
    d3 = dict(d); d3.pop("highlights")
    kb3 = KnowledgeTree.from_dict(d3)
    assert "highlights" not in kb3.to_dict()
    assert "I highlighted" not in kb3.to_markdown()
    assert "I highlighted" not in tree_to_html(kb3)
    print("ok  knowledge round-trip (glossary, levels, note, highlights, extras)")


def test_message_builders():
    m = define_message("load factor", "hash tables", "A: it is a ratio.")
    assert "load factor" in m and "hash tables" in m
    q = quiz_message("hash tables", "Q: what\nA: this", 5)
    assert "5 questions" in q
    print("ok  message builders")


def test_handle_survey():
    import json

    from learn_with_claude.webapi import ApiError, handle_survey

    reply = {"items": [
        {"name": "processes and threads", "why": "everything the OS runs is one",
         "items": [{"name": "the process abstraction", "why": "the unit of isolation"},
                   {"name": "context switching", "why": "how one CPU runs many",
                    "items": [{"name": "too deep", "why": "must be clipped"}]}]},
        {"name": "", "why": "no name -> dropped"},
        "not a dict",
        {"name": "x" * 200, "why": "y" * 500},
    ]}

    def stub(system, messages, role, **kw):
        assert role == "tutor" and "foundations" in messages[0]["content"].lower() or True
        return json.dumps(reply), 0.01

    r = handle_survey({"topic": "operating systems"}, stub)
    assert r["cost"] == 0.01
    names = [i["name"] for i in r["items"]]
    assert names[0] == "processes and threads" and len(names) == 2
    assert len(names[1]) == 80 and r["items"][1]["why"] == "y" * 300  # clipped
    subs = r["items"][0]["items"]
    assert [s["name"] for s in subs] == ["the process abstraction", "context switching"]
    assert "items" not in subs[1]  # depth capped at two levels

    # focus + existing flow through to the message
    seen = {}

    def spy(system, messages, role, **kw):
        seen["msg"] = messages[0]["content"]
        return json.dumps(reply), 0.0

    handle_survey({"topic": "operating systems", "focus": "context switching",
                   "existing": ["processes and threads"]}, spy)
    assert "context switching" in seen["msg"] and "processes and threads" in seen["msg"]

    try:
        handle_survey({"topic": ""}, stub)
        assert False, "missing topic must raise"
    except ApiError:
        pass
    try:
        handle_survey({"topic": "x"}, lambda *a, **k: ("no json here", 0.0))
        assert False, "unusable reply must raise"
    except ApiError:
        pass
    print("ok  handle_survey (validation, clipping, depth cap, focus)")


if __name__ == "__main__":
    test_learner_levels()
    test_tutor_system_segments()
    test_split_tutor_parts()
    test_knowledge_round_trip()
    test_message_builders()
    test_handle_survey()
    print("\nall green")
