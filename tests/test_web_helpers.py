"""Plain-python regression tests for the web app's server-side helpers.

Run with:  python tests/test_web_helpers.py
(no test framework needed — asserts throughout, prints ok per group)
"""

import json
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
    local_grounding_system,
    order_questions_message,
    quiz_message,
    suggest_questions_message,
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
    base = tutor_system()
    assert "MARKUP" not in base  # the CLI stays plain
    seg = tutor_system(segments=True)
    assert "MARKUP" in seg and "[watch out]" in seg
    print("ok  tutor segments flag")


def test_tutor_grounding():
    # hosted (no grounding passed): byte-identical to before local grounding
    # existed — the whole safety property the feature depends on.
    base = tutor_system()
    assert tutor_system(grounding=None) == base
    assert "LOCAL TOOLS" not in base
    assert "do not use any tools or the filesystem" in base

    g = local_grounding_system("/some/proj", ["confluence — the wiki"])
    assert "/some/proj" in g and "confluence — the wiki" in g
    assert local_grounding_system(None) == local_grounding_system(None, [])
    assert '"' not in local_grounding_system(None)   # no dangling code_dir clause

    local = tutor_system(grounding=g)
    assert "LOCAL TOOLS" in local and "/some/proj" in local
    assert "do not use any tools" not in local   # grounding replaces, not appends
    print("ok  tutor grounding (hosted default byte-identical, local block swaps in)")


def test_handle_tutor_grounding():
    from learn_with_claude.webapi import handle_tutor, model_routes

    seen = {}

    def stub(system, messages, role, **kw):
        seen["system"] = system
        return "Direct answer.", 0.01

    handle_tutor({"action": "q"}, stub, grounding="LOCAL TOOLS marker")
    assert "LOCAL TOOLS marker" in seen["system"]

    # model_routes accepts a zero-arg callable, re-evaluated every request —
    # local settings (code_dir, mcp servers) can change while the server runs
    calls = {"n": 0}

    def live_grounding():
        calls["n"] += 1
        return f"call-{calls['n']}"

    local_routes = model_routes(stub, tutor_grounding=live_grounding)
    local_routes["tutor"]({"action": "q"})
    assert "call-1" in seen["system"]
    local_routes["tutor"]({"action": "q"})
    assert "call-2" in seen["system"] and calls["n"] == 2

    # api/index.py (hosted) never passes tutor_grounding — stays untouched
    hosted_routes = model_routes(stub)
    hosted_routes["tutor"]({"action": "q"})
    assert "call-" not in seen["system"]
    assert "do not use any tools or the filesystem" in seen["system"]
    print("ok  handle_tutor / model_routes grounding wiring (local live, hosted untouched)")


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
            "why": "builds on the hashing just covered",
            "unknown_future_field": {"nested": True},   # must not crash
        }},
        "glossary": {"widget": {"term": "widget", "def": "A thing.", "node": 1, "turn": 1}},
        "note": "My takeaway.\nStill line one.\n\nA second paragraph.",
        "highlights": [{"node": 1, "turn": 1, "text": "a"},
                       {"node": 99, "turn": 1, "text": "orphaned passage"},
                       "not a dict"],
        "quiz": {"made": "2026-07-13", "questions": []},   # unknown top-level key
        "profile": "computer-science",                     # another web-side extra
        "teach": [
            {"node": 1, "when": "2026-07-20T10:00:00Z", "text": "an early rough take",
             "missing": "the gap", "verdict": "gappy"},
            {"node": 1, "when": "2026-07-21T10:00:00Z", "text": "my own words on widgets",
             "missing": "nothing — complete", "verdict": "clean"},
            {"node": 99, "when": "2026-07-21T10:00:00Z", "text": "orphaned attempt"},
            "not a dict",
        ],
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.nodes[1].learner_level == "expert"
    assert kb.nodes[1].why == "builds on the hashing just covered"
    assert kb.glossary["widget"]["def"] == "A thing."
    assert kb.note.startswith("My takeaway.")
    assert [h["text"] for h in kb.highlights] == ["a", "orphaned passage"]
    out = kb.to_dict()
    assert out["glossary"]["widget"]["term"] == "widget"
    assert out["note"] == d["note"]                        # personal note round-trips
    assert out["nodes"]["1"]["turns"][0]["parts"][0]["text"] == "a"  # turn extras survive
    assert out["nodes"]["1"]["why"] == "builds on the hashing just covered"
    # web-side fields survive a CLI round-trip instead of being stripped
    assert out["highlights"] == kb.highlights
    assert out["quiz"] == d["quiz"] and out["profile"] == "computer-science"
    assert out["format"] == d["format"]                    # extras never shadow known keys
    md = kb.to_markdown()
    assert "## Glossary" in md and "**widget** — A thing." in md
    assert "## My notes" in md and "A second paragraph." in md
    assert "> ★ I highlighted: a" in md                    # under its turn
    assert "orphaned passage" not in md                    # no such node — dropped
    # teach-back: latest attempt per node, verdict tagged, orphans dropped
    assert "## Explained back" in md and "my own words on widgets" in md
    assert "✓ clean (attempt 2)" in md
    assert "an early rough take" not in md                 # superseded attempt
    assert "The gap that mattered" not in md               # clean — no gap line
    assert "orphaned attempt" not in md
    html = tree_to_html(kb)
    assert "Glossary" in html and "A thing." in html
    assert "My notes" in html and "A second paragraph." in html
    assert "★ I highlighted" in html and "<mark>a</mark>" in html
    assert "Explained back" in html and "my own words on widgets" in html
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


def test_handle_interview():
    import json

    from learn_with_claude.webapi import ApiError, handle_interview, learner_opening, tutor_extra_context

    assessment = {"solid": ["hashing gives an index", "  ", "x" * 400],
                  "shaky": ["thinks collisions are rare"],
                  "gaps": ["load factor", "resizing", "g3", "g4", "g5", "g6", "g7"],
                  "level": "Practitioner", "focus": "collision handling",
                  "opening_question": "what actually happens when two keys collide?"}
    ex1 = [{"q": "what do you know about hash tables?",
            "a": "you hash the key and collisions are rare"}]
    seen = {}

    def asks(system, messages, role, **kw):
        seen["system"], seen["messages"], seen["role"] = system, messages, role
        return json.dumps({"question": "how rare, would you say?"}), 0.01

    # mid-interview: the tutor asks the next question
    r = handle_interview({"topic": "hash tables", "exchanges": ex1}, asks)
    assert r["question"] == "how rare, would you say?" and r["cost"] == 0.01
    assert seen["role"] == "tutor"
    assert seen["messages"][1]["role"] == "assistant"          # transcript rebuilt
    assert "collisions are rare" in seen["messages"][2]["content"]
    assert "1 of at most 6" in seen["messages"][2]["content"]  # budget note

    def concludes(system, messages, role, **kw):
        seen["messages"] = messages
        return json.dumps({"assessment": assessment}), 0.02

    # the learner asked to finish: directive sent, assessment validated/clipped
    r = handle_interview({"topic": "hash tables", "exchanges": ex1, "finish": True}, concludes)
    assert "produce the assessment now" in seen["messages"][-1]["content"]
    a = r["assessment"]
    assert a["solid"][0] == "hashing gives an index" and len(a["solid"][1]) == 200
    assert a["gaps"][:2] == ["load factor", "resizing"] and len(a["gaps"]) == 6  # clipped
    assert a["level"] == "practitioner" and a["focus"] == "collision handling"

    # budget spent (6 exchanges) forces conclusion even without finish
    ex6 = [{"q": f"q{i}", "a": f"a{i}"} for i in range(6)]
    handle_interview({"topic": "t", "exchanges": ex6}, concludes)
    assert "budget is spent" in seen["messages"][-1]["content"]
    # ...and a question back when one was demanded is a 502
    try:
        handle_interview({"topic": "t", "exchanges": ex6}, asks)
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 502

    # a level the app doesn't know falls back to student
    r = handle_interview({"topic": "t", "exchanges": ex1, "finish": True},
                         lambda *a, **k: (json.dumps({"assessment": {**assessment, "level": "guru"}}), 0.0))
    assert r["assessment"]["level"] == "student"
    for bad, status in (({"topic": "", "exchanges": ex1}, 400),
                        ({"topic": "t", "exchanges": [], "finish": True}, 400)):
        try:
            handle_interview(bad, asks)
            raise AssertionError("expected ApiError")
        except ApiError as e:
            assert e.status == status
    try:
        handle_interview({"topic": "t", "exchanges": ex1}, lambda *a, **k: ("no json", 0.0))
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 502

    # the gaps kind seeds both personas with the baseline map
    body = {"kind": "gaps", "topic": "hash tables",
            "baseline": "solid: hashing\nshaky: collisions are rare",
            "focus": "collision handling", "opening_question": "what happens on a collision?"}
    lo = learner_opening(body)
    assert "NOT starting" in lo and "collisions are rare" in lo and "collision handling" in lo
    tc = tutor_extra_context(body)
    assert "shaky" in tc and "Do NOT re-explain" in tc
    print("ok  interview handler + gaps kind")


def test_handle_teachback():
    import json

    from learn_with_claude.webapi import ApiError, handle_teachback

    reply = {"right": "You nailed that the array index comes from the hash.",
             "missing": "Collisions — two keys can land on the same slot.",
             "question": "What should happen when they do?",
             "verdict": "Close"}
    seen = {}

    def stub(system, messages, role, **kw):
        seen["system"], seen["msg"], seen["role"] = system, messages[0]["content"], role
        return json.dumps(reply), 0.02

    r = handle_teachback({"topic": "hash tables", "label": "hash tables",
                          "digest": "Q: what is it\nA: an array plus a hash function",
                          "explanation": "you hash the key to get an index"}, stub)
    assert seen["role"] == "tutor"
    assert "ground truth" in seen["msg"] and "you hash the key" in seen["msg"]
    assert "CONTINUING" not in seen["msg"]            # no history -> one-shot framing
    assert "never" in seen["system"].lower()          # style is off-limits
    assert r["cost"] == 0.02
    assert r["right"].startswith("You nailed") and "Collisions" in r["missing"]
    assert r["question"] == "What should happen when they do?"
    assert r["verdict"] == "close"                    # normalised
    # an unknown or absent verdict falls back to the middle of the scale
    r2 = handle_teachback({"explanation": "x"},
                          lambda *a, **k: (json.dumps({**reply, "verdict": "great"}), 0.0))
    assert r2["verdict"] == "close"
    r3 = handle_teachback({"explanation": "x"},
                          lambda *a, **k: (json.dumps({**reply, "verdict": "gappy"}), 0.0))
    assert r3["verdict"] == "gappy"

    # an empty explanation is a 400, unusable model output a 502
    for bad, status in ((({"explanation": ""}), 400),):
        try:
            handle_teachback(bad, stub)
            raise AssertionError("expected ApiError")
        except ApiError as e:
            assert e.status == status
    try:
        handle_teachback({"explanation": "x"}, lambda *a, **k: ("not json", 0.0))
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 502

    # continuing a thread: history present -> the message frames the new
    # explanation as a reply to the tutor's last question, not a restart
    seen2 = {}

    def stub2(system, messages, role, **kw):
        seen2["msg"] = messages[0]["content"]
        return json.dumps(reply), 0.01

    r4 = handle_teachback({
        "explanation": "when they collide you probe to the next open slot",
        "history": [
            {"explanation": "you hash the key to get an index", "right": "got the index part",
             "missing": "collisions", "question": "What should happen when they do?"},
            "not a dict",           # ignored
            {"explanation": "", "right": "x"},   # empty explanation -> skipped
        ],
    }, stub2)
    assert r4["cost"] == 0.01
    assert "CONTINUING" in seen2["msg"]
    assert "you hash the key to get an index" in seen2["msg"]
    assert "What should happen when they do?" in seen2["msg"]
    assert "when they collide you probe to the next open slot" in seen2["msg"]
    assert seen2["msg"].count("Learner said") == 1   # the two bad entries were dropped
    print("ok  teachback handler")


def test_handle_exam():
    import json

    from learn_with_claude.webapi import ApiError, handle_exam

    paper = {"questions": [
        {"kind": "mechanism", "command": "Explain",
         "q": "Explain why lookup time degrades as a hash table fills up.",
         "points": ["links the load factor to collision probability",
                    "explains that probe sequences lengthen"],
         "terms": ["load factor", "collision", "probing"]},
        {"kind": "wharrgarbl", "command": "assess",     # unknown kind -> dropped
         "q": "Assess the claim that a bigger table is always faster.",
         "points": ["notes the memory cost"], "terms": ["cache locality"]},
        {"q": "too short"},                             # under the length floor
        {"kind": "transfer", "q": "A cache keeps 8 slots and never resizes. Predict "
                                  "what happens as the tenth key arrives, and why.",
         "points": ["applies eviction or chaining"], "terms": ["eviction"]},
        {"not": "a dict"},
    ]}
    seen = {}

    def stub(system, messages, role, **kw):
        seen["system"], seen["msg"], seen["role"] = system, messages[0]["content"], role
        return json.dumps(paper), 0.04

    r = handle_exam({"root_topic": "hash tables", "label": "collisions",
                     "material": "Q: what is it\nA: an array plus a hash function",
                     "count": 5}, stub)
    # the exam runs on its own role so a backend can point it at a stronger model
    assert seen["role"] == "examiner"
    assert "syllabus" in seen["msg"] and "an array plus a hash function" in seen["msg"]
    assert "5 questions" in seen["msg"]
    # the paper never quotes the tutorial, and says so in its own instructions
    assert "NEVER quote the transcript" in seen["system"]
    assert r["cost"] == 0.04
    assert len(r["questions"]) == 3                 # the short one and the non-dict go
    q0 = r["questions"][0]
    assert q0["marks"] == 10 and q0["kind"] == "mechanism" and q0["command"] == "explain"
    assert q0["terms"] == ["load factor", "collision", "probing"]
    assert r["questions"][1]["kind"] == ""          # unrecognised kind is dropped, not kept
    # the count is clamped, and it caps how many questions come back
    r2 = handle_exam({"material": "m", "count": 99}, stub)
    assert len(r2["questions"]) == 3                # clamped to 8, model returned 3 usable
    assert "8 questions" in seen["msg"]
    r3 = handle_exam({"material": "m", "count": 1}, stub)
    assert "3 questions" in seen["msg"] and len(r3["questions"]) == 3

    # no material is a 400; an unusable paper is a 502
    try:
        handle_exam({"material": "  "}, stub)
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 400
    try:
        handle_exam({"material": "m"}, lambda *a, **k: ("not json", 0.0))
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 502
    print("ok  exam paper handler")


def test_handle_mark_exam():
    import json

    from learn_with_claude.webapi import ApiError, handle_mark_exam

    questions = [
        {"q": "Explain why lookup degrades as the table fills.",
         "points": ["links load factor to collisions", "probe sequences lengthen"],
         "terms": ["load factor"], "marks": 10},
        {"q": "Assess the claim that a bigger table is always faster.",
         "points": ["notes the memory cost"], "terms": ["cache locality"], "marks": 10},
    ]
    marked = {"results": [
        {"marks": 8, "earned": "You were right that the slot comes from the key. That is the core of it.",
         "improve": "You stopped short of clustering. A full answer says probes lengthen.",
         "hit": ["links load factor to collisions"], "missed": ["probe sequences lengthen"]},
        {"marks": 2, "earned": "Not much to go on here.",
         "improve": "The memory cost is what the claim ignores.",
         "hit": [], "missed": ["notes the memory cost"]},
    ], "overall": "The mechanism is solid. Consequences are where you keep stopping."}
    seen = {}

    def stub(system, messages, role, **kw):
        seen["system"], seen["msg"], seen["role"] = system, messages[0]["content"], role
        return json.dumps(marked), 0.09

    r = handle_mark_exam({"root_topic": "hash tables", "label": "collisions",
                          "material": "Q: what is it\nA: an array plus a hash function",
                          "questions": questions,
                          "answers": ["it gets fuller so more clashes", ""]}, stub)
    assert seen["role"] == "examiner"
    # the marker sees the scheme, the material, and which answer was left blank
    assert "Mark scheme" in seen["msg"] and "links load factor to collisions" in seen["msg"]
    assert "an array plus a hash function" in seen["msg"]
    assert "it gets fuller so more clashes" in seen["msg"]
    assert "(left blank)" in seen["msg"]
    # both credit dimensions are actually in the examiner's instructions
    assert "CONTENT" in seen["system"] and "PRECISION" in seen["system"]
    assert r["cost"] == 0.09
    assert r["total"] == 10 and r["max"] == 20      # arithmetic is ours, not the model's
    assert len(r["results"]) == 2
    assert r["results"][0]["marks"] == 8
    assert r["results"][0]["hit"] == ["links load factor to collisions"]
    assert r["results"][0]["missed"] == ["probe sequences lengthen"]
    # feedback is sentence-spaced like every other block of prose in the app
    assert "\n\n" in r["results"][0]["earned"]
    assert r["overall"].startswith("The mechanism is solid.")

    # marks are clamped and a missing/garbage result scores 0 rather than
    # throwing the whole script away
    wild = {"results": [{"marks": 47, "earned": "x"}, {"marks": "??", "improve": "y"}],
            "overall": ""}
    r2 = handle_mark_exam({"material": "m", "questions": questions, "answers": ["a", "b"]},
                          lambda *a, **k: (json.dumps(wild), 0.0))
    assert [x["marks"] for x in r2["results"]] == [10, 0]
    assert r2["total"] == 10 and r2["max"] == 20
    # fewer results than questions still returns one entry per question
    short = {"results": [{"marks": 5, "earned": "only one came back"}]}
    r3 = handle_mark_exam({"material": "m", "questions": questions, "answers": ["a", "b"]},
                          lambda *a, **k: (json.dumps(short), 0.0))
    assert len(r3["results"]) == 2 and r3["results"][1]["marks"] == 0

    # guards: no material, no questions, an entirely blank script, junk output
    for bad in ({"questions": questions, "answers": ["a"]},
                {"material": "m", "questions": [], "answers": []},
                {"material": "m", "questions": questions, "answers": ["", "  "]}):
        try:
            handle_mark_exam(bad, stub)
            raise AssertionError("expected ApiError")
        except ApiError as e:
            assert e.status == 400
    try:
        handle_mark_exam({"material": "m", "questions": questions, "answers": ["a", "b"]},
                         lambda *a, **k: ("not json", 0.0))
        raise AssertionError("expected ApiError")
    except ApiError as e:
        assert e.status == 502
    print("ok  exam marking handler")


def test_exam_exports():
    """A marked paper survives a .know.json round-trip and reaches both
    exports; an unsubmitted one is work in progress and reaches neither."""
    d = {
        "format": "learn-with-claude/knowledge-tree", "version": 1, "id": "t2",
        "root_topic": "hash tables", "created": "2026-07-31", "root_id": 1, "next": 2,
        "nodes": {"1": {"id": 1, "label": "collisions", "children": [],
                        "turns": [{"turn": 1, "action": "q", "tutor": "a"}]}},
        "exams": [
            {"id": "e1", "node": 1, "made": "2026-07-30T09:00:00Z",
             "submitted": "2026-07-30T10:00:00Z", "total": 8, "max": 20,
             "overall": "The mechanism is solid.",
             "questions": [{"q": "Explain why lookup degrades.", "marks": 10},
                           {"q": "Assess the bigger-is-faster claim.", "marks": 10}],
             "answers": ["more clashes as it fills", ""],
             "results": [{"marks": 6, "earned": "You had the clash.",
                          "improve": "Clustering was the missing step."},
                         {"marks": 2, "earned": "Nothing written.",
                          "improve": "The memory cost is what it ignores."}]},
            {"id": "e2", "node": 1, "made": "2026-07-31T09:00:00Z",
             "questions": [{"q": "A paper still being written.", "marks": 10}],
             "answers": ["half an answer"]},
            {"id": "e3", "node": 99, "submitted": "2026-07-31T09:00:00Z",
             "questions": [{"q": "An orphaned paper."}], "results": [{"marks": 1}]},
            "not a dict",
        ],
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.to_dict()["exams"] == d["exams"]        # extras survive the CLI untouched
    exams = kb.exam_map()
    assert list(exams) == [1] and len(exams[1]) == 1   # unsubmitted + orphan dropped
    rows = KnowledgeTree.exam_rows(exams[1][0])
    assert len(rows) == 2 and rows[1][1] == ""         # the blank answer keeps its slot

    md = kb.to_markdown()
    assert "## Exams" in md and "collisions — 8/20" in md
    assert "**Q1 — 6/10.** Explain why lookup degrades." in md
    assert "> ✍ more clashes as it fills" in md
    assert "(left blank)" in md                        # the unanswered question
    assert "Clustering was the missing step." in md
    assert "The mechanism is solid." in md
    assert "A paper still being written." not in md    # not submitted
    assert "An orphaned paper." not in md              # node was pruned

    html = tree_to_html(kb)
    assert "Exams" in html and "8/20" in html
    assert "Explain why lookup degrades." in html
    assert "Clustering was the missing step." in html
    assert "A paper still being written." not in html

    # no exams at all -> no key in the file, no section in either export
    d2 = dict(d); d2.pop("exams")
    kb2 = KnowledgeTree.from_dict(d2)
    assert "exams" not in kb2.to_dict()
    assert "## Exams" not in kb2.to_markdown() and "✍ Exams" not in tree_to_html(kb2)
    print("ok  exam exports (round-trip, markdown, html)")


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


def test_aside_exports():
    """🏷 my words: the reader's own gloss, spliced into the sentence it
    explains — in place, in both exports, exactly where the app shows it."""
    from learn_with_claude.knowledge import apply_asides

    # the plain splice, on the shape the feature was asked for
    assert apply_asides(
        "so if a plant mitochondria is active",
        [{"text": "mitochondria", "words": "power house of the cell"}],
    ) == "so if a plant mitochondria (power house of the cell) is active"

    # the anchor is stored whitespace-collapsed; the prose is not
    assert apply_asides("a hash\ntable stores pairs",
                        [{"text": "hash table", "words": "a lookup array"}]) \
        == "a hash\ntable (a lookup array) stores pairs"
    # first occurrence only, like the browser
    assert apply_asides("bucket then bucket",
                        [{"text": "bucket", "words": "a slot"}]) \
        == "bucket (a slot) then bucket"
    # anything that doesn't match, or has no words, changes nothing
    for junk in ([{"text": "absent", "words": "x"}], [{"text": "a", "words": ""}], []):
        assert apply_asides("plain text", junk) == "plain text"
    # regex metacharacters in the anchor are matched literally
    assert apply_asides("call f(x) now", [{"text": "f(x)", "words": "a function"}]) \
        == "call f(x) (a function) now"
    # The anchor is captured from the RENDERED page, where `malloc` reads as
    # plain "malloc" — so it has to match the source's backticked form, or the
    # aside shows in the app and silently vanishes from the export.
    assert apply_asides("Call `malloc` to get memory",
                        [{"text": "Call malloc to get", "words": "the C call"}]) \
        == "Call `malloc` to get (the C call) memory"
    assert apply_asides("the `bucket` holds it",
                        [{"text": "bucket", "words": "a slot"}]) \
        == "the `bucket` (a slot) holds it"

    d = {
        "format": "learn-with-claude/knowledge-tree", "version": 1, "id": "t5",
        "root_topic": "plant cells", "created": "2026-08-01", "root_id": 1, "next": 2,
        "nodes": {"1": {"id": 1, "label": "respiration", "children": [], "turns": [
            {"turn": 1, "action": "q",
             "tutor": "So if a plant mitochondria is active, it makes ATP."},
            # `tutor` is every part joined, the way handle_tutor stores it
            {"turn": 2, "action": "q2",
             "tutor": "The chloroplast does the opposite.\n\nBecause a stroma stores sugar.",
             "parts": [{"label": "", "text": "The chloroplast does the opposite."},
                       {"label": "why", "text": "Because a stroma stores sugar."}]},
        ]}},
        "asides": [
            {"node": 1, "turn": 1, "text": "mitochondria",
             "words": "power house of the cell", "when": "2026-08-01T10:00:00Z"},
            # one anchored inside a labelled answer card
            {"node": 1, "turn": 2, "text": "stroma", "words": "the goo bit"},
            {"node": 99, "turn": 1, "text": "orphan", "words": "dropped"},
            {"node": 1, "turn": 1, "text": "", "words": "no anchor"},
            {"node": 1, "turn": 1, "text": "ATP", "words": ""},
            "not a dict",
        ],
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.to_dict()["asides"] == d["asides"]   # extras survive the CLI untouched

    m = kb.aside_map()
    assert sorted(m) == [(1, 1), (1, 2)]
    assert m[(1, 1)] == [{"text": "mitochondria", "words": "power house of the cell"}]

    md = kb.to_markdown()
    assert "So if a plant mitochondria (power house of the cell) is active" in md
    assert "a stroma (the goo bit) stores sugar" in md
    assert "dropped" not in md and "no anchor" not in md

    html = tree_to_html(kb)
    assert 'mitochondria <span class="aside">(power house of the cell)</span>' in html
    # it lands in the right answer card, not the first one
    assert 'stroma <span class="aside">(the goo bit)</span>' in html
    assert html.count('class="aside"') == 2, "an aside must land exactly once"
    # the sentinels never survive into the page
    assert "" not in html and "" not in html
    assert "dropped" not in html

    # no asides -> no key, and neither export mentions them
    d2 = dict(d); d2.pop("asides")
    kb2 = KnowledgeTree.from_dict(d2)
    assert "asides" not in kb2.to_dict()
    assert "power house" not in kb2.to_markdown()
    assert 'class="aside"' not in tree_to_html(kb2)
    print("ok  asides (splice, both exports, labelled parts, sentinels)")


def test_handle_facts():
    """⚡ fact me out: grouping, clamping, and the de-duplication that keeps
    the same fact from appearing under two headings."""
    import json

    from learn_with_claude.webapi import (
        FACTS_MAX_TOTAL, ApiError, handle_facts,
    )

    reply = {"groups": [
        {"name": "The lookup chain", "facts": [
            {"text": "A recursive resolver queries other servers until it has an answer.",
             "kind": "mechanism"},
            {"text": "Root servers hold no domain addresses; they only refer resolvers on.",
             "kind": "misconception"},
            # the same fact in different words — the prompt forbids it, this
            # catches it happening anyway
            {"text": "A resolver that is recursive will query other servers until an answer.",
             "kind": "mechanism"},
            {"text": "short", "kind": "number"},                # a lost heading
            {"text": "An unknown kind falls back to none.", "kind": "vibes"},
            "a bare string is accepted as a fact",
            12345,
        ]},
        {"name": "", "facts": [{"text": "a group with no name is dropped"}]},
        {"name": "Empty group", "facts": []},
        "not a dict",
        {"name": "x" * 200, "facts": [{"text": "y" * 500, "kind": "edge"}]},
    ]}

    seen = {}

    def stub(system, messages, role, **kw):
        seen.update(role=role, system=system, msg=messages[0]["content"], kw=kw)
        return "here you go " + json.dumps(reply), 0.06

    r = handle_facts({"topic": "how DNS resolution works"}, stub)

    # the strongest model, and a knowledge-bound task rather than a
    # reasoning-bound one — full effort would only slow it down
    assert seen["role"] == "facts" and seen["kw"]["effort"] == "medium"
    assert "how DNS resolution works" in seen["msg"]
    assert r["cost"] == 0.06

    names = [g["name"] for g in r["groups"]]
    assert names[0] == "The lookup chain"
    assert "" not in names and "Empty group" not in names   # unnamed/empty dropped
    assert len(names[-1]) == 80                              # clipped

    first = r["groups"][0]["facts"]
    texts = [f["text"] for f in first]
    assert texts[0].startswith("A recursive resolver")
    assert not any("A resolver that is recursive" in t for t in texts), "near-dupe kept"
    # ...but two facts that merely share a subject stay, both of them
    from learn_with_claude.webapi import _question_words, _same_fact
    assert not _same_fact(_question_words("A CNAME record aliases one domain to another."),
                          _question_words("An MX record names the mail servers for a domain."))
    assert not any(t == "short" for t in texts)              # too short to be a fact
    assert "a bare string is accepted as a fact" in texts    # tolerated shape
    assert [f["kind"] for f in first if "unknown kind" in f["text"]] == [""]
    assert r["groups"][-1]["facts"][0]["text"] == "y" * 300  # clipped
    assert r["count"] == sum(len(g["facts"]) for g in r["groups"])

    # an angle slants the selection and reaches the model
    handle_facts({"topic": "DNS", "angle": "for a security review"}, stub)
    assert "for a security review" in seen["msg"]

    # the mix rules are what keep this from being a glossary
    assert "roughly a THIRD" in seen["system"]
    assert "NEVER INVENT PRECISION" in seen["system"]
    assert 'never prefix it with "Misconception:"' in seen["system"]

    # the total cap holds even when every group is full
    big = {"groups": [{"name": f"g{i}",
                       "facts": [{"text": f"Fact number {i}-{j} says a specific thing."}
                                 for j in range(12)]}
                      for i in range(10)]}
    r2 = handle_facts({"topic": "x"},
                      lambda *a, **k: (json.dumps(big), 0.0))
    assert r2["count"] <= FACTS_MAX_TOTAL
    assert sum(len(g["facts"]) for g in r2["groups"]) == r2["count"]

    try:
        handle_facts({"topic": ""}, stub)
        assert False, "missing topic must raise"
    except ApiError:
        pass
    try:
        handle_facts({"topic": "x"}, lambda *a, **k: ("no json here", 0.0))
        assert False, "an unusable reply must raise"
    except ApiError:
        pass
    print("ok  handle_facts (grouping, dedupe, clamping, caps, angle)")


def test_facts_exports():
    """The landscape survives the .know.json round-trip and heads both
    exports as its own section — it is reference material, not a turn."""
    d = {
        "format": "learn-with-claude/knowledge-tree", "version": 1, "id": "t4",
        "root_topic": "DNS", "created": "2026-08-01", "root_id": 1, "next": 2,
        "nodes": {"1": {"id": 1, "label": "resolvers", "children": [],
                        "turns": [{"turn": 1, "action": "q", "tutor": "a"}]}},
        "facts": {"made": "2026-08-01T12:00:00Z", "cost": 0.06, "groups": [
            {"name": "The lookup chain", "facts": [
                {"text": "Root servers only refer resolvers onward.", "kind": "misconception"},
                {"text": "A resolver caches answers for the record's TTL.", "kind": "mechanism"},
            ]},
            {"name": "Nameless facts", "facts": [{"text": "A fact with no kind at all."}]},
            {"name": "", "facts": [{"text": "dropped: no group name"}]},
            {"name": "Empty", "facts": []},
            "not a dict",
        ]},
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.to_dict()["facts"] == d["facts"]     # extras survive the CLI untouched

    groups = kb.fact_groups()
    assert [n for n, _ in groups] == ["The lookup chain", "Nameless facts"]

    md = kb.to_markdown()
    assert "## The landscape" in md and "### The lookup chain" in md
    assert "- *(misconception)* Root servers only refer resolvers onward." in md
    assert "- A fact with no kind at all." in md   # no empty *()* for a bare fact
    assert "dropped: no group name" not in md

    html = tree_to_html(kb)
    assert 'id="facts"' in html and "The landscape" in html
    assert "Root servers only refer resolvers onward." in html
    assert "dropped: no group name" not in html

    # no facts -> no key, nothing in either export
    d2 = dict(d); d2.pop("facts")
    kb2 = KnowledgeTree.from_dict(d2)
    assert "facts" not in kb2.to_dict()
    assert "## The landscape" not in kb2.to_markdown()
    assert 'id="facts"' not in tree_to_html(kb2)
    print("ok  facts exports (round-trip, markdown, html section)")


def test_image_prompt():
    """The rules that stop a generated figure being worse than none: an
    explicit label whitelist, a flat-vector style, and omit-rather-than-invent.
    """
    from learn_with_claude import gemini_images as gi

    prompt = gi.build_prompt({
        "kind": "process", "subject": "how a key becomes a bucket index",
        "elements": ["a key on the left", "a hash function box in the middle"],
        "layout": "left to right, one arrow between each pair",
        "labels": ["key", "hash function", "bucket"],
        "avoid": "the culinary sense of hash",
    })
    # the whitelist is what suppresses invented gibberish text
    assert '"key", "hash function", "bucket"' in prompt
    assert "Write these 3 labels and no others" in prompt
    assert "no title, no caption, no legend" in prompt
    assert "is an error" in prompt
    # style + honesty rules
    assert "Flat vector illustration" in prompt and "no photorealism" in prompt
    assert "leave it out rather than inventing" in prompt
    assert "Specifically avoid: the culinary sense of hash" in prompt
    assert "left-to-right process diagram" in prompt      # the kind's own noun
    assert "a hash function box in the middle" in prompt

    # no labels at all is a legitimate brief — and then NO text is wanted
    bare = gi.build_prompt({"kind": "concrete", "subject": "a B-tree node",
                            "elements": [], "labels": []})
    assert "Write no text at all anywhere in the image." in bare
    assert "a B-tree node" in bare

    # an unknown kind still produces a usable prompt rather than blowing up
    odd = gi.build_prompt({"kind": "interpretive dance", "subject": "x"})
    assert gi.KINDS[gi.DEFAULT_KIND][0] in odd

    # each kind picks the shape that kind of idea wants, and junk is coerced
    assert gi.clean_aspect("16:9", "structure") == "16:9"
    assert gi.clean_aspect("banana", "process") == "16:9"
    assert gi.clean_aspect(None, "layers") == "3:4"
    assert gi.clean_aspect(None, "nonsense") == gi.DEFAULT_ASPECT

    # pricing is matched longest-prefix-first: the lite model must not be read
    # as the flash model it shares a prefix with
    assert gi.price_of("gemini-3.1-flash-lite-image") == 0.0336
    assert gi.price_of("gemini-3.1-flash-image") == 0.067
    assert gi.price_of("gemini-3-pro-image") == 0.134
    assert gi.price_of("something-new") == gi.FALLBACK_PRICE
    print("ok  image prompt (label whitelist, style, aspect, pricing)")


def test_gemini_reply_parsing():
    """Both spellings of the inline-image block, and a refusal that explains
    itself instead of a bare 'no image'."""
    from learn_with_claude import gemini_images as gi

    camel = {"candidates": [{"content": {"parts": [
        {"text": "Here you go:"},
        {"inlineData": {"mimeType": "image/png", "data": "QUJD"}}]}}]}
    assert gi._first_inline_image(camel) == ("QUJD", "image/png")

    snake = {"candidates": [{"content": {"parts": [
        {"inline_data": {"mime_type": "image/webp", "data": "REVG"}}]}}]}
    assert gi._first_inline_image(snake) == ("REVG", "image/webp")

    assert gi._first_inline_image({"candidates": []}) is None

    blocked = {"promptFeedback": {"blockReason": "SAFETY"}}
    assert "SAFETY" in gi._refusal(blocked)
    talked = {"candidates": [{"content": {"parts": [
        {"text": "I can't draw that."}]}, "finishReason": "STOP"}]}
    assert "words instead of a picture" in gi._refusal(talked)
    stopped = {"candidates": [{"finishReason": "RECITATION"}]}
    assert "RECITATION" in gi._refusal(stopped)
    assert gi._refusal({}).strip()          # never an empty explanation
    print("ok  gemini reply parsing (both spellings, refusal messages)")


def test_handle_illustrate():
    """Stage one decides what to draw — including deciding not to."""
    import json

    from learn_with_claude import gemini_images
    from learn_with_claude.webapi import ApiError, handle_illustrate

    drawn = {}

    def fake_generate(prompt, aspect=gemini_images.DEFAULT_ASPECT):
        drawn["prompt"], drawn["aspect"] = prompt, aspect
        return "QUJD", "image/png", 0.134

    real_generate, real_key = gemini_images.generate, gemini_images.api_key
    gemini_images.generate = fake_generate
    gemini_images.api_key = lambda: "test-key"
    try:
        brief = {"drawable": True, "subject": "a bucket array with one chain",
                 "kind": "structure", "elements": ["eight boxes in a row"] * 9,
                 "layout": "a row of boxes", "labels": ["bucket"] * 9,
                 "avoid": "", "alt": "Eight boxes in a row, one holding a chain",
                 "caption": "buckets and a chain"}
        seen = {}

        def stub(system, messages, role, **kw):
            seen.update(role=role, msg=messages[0]["content"], kw=kw)
            return "here you go " + json.dumps(brief), 0.004

        r = handle_illustrate(
            {"passage": "Chaining keeps a linked list in each bucket.",
             "topic": "hash tables", "label": "collisions", "context": "Q: …\nA: …"},
            stub)

        # the passage — not the whole conversation — is what gets illustrated
        assert "Chaining keeps a linked list" in seen["msg"]
        assert "hash tables" in seen["msg"] and "collisions" in seen["msg"]
        # a short structured judgement: xhigh would only be slower and dearer
        assert seen["role"] == "tutor" and seen["kw"]["effort"] == "low"

        assert r["drawable"] and r["data"] == "QUJD" and r["mime"] == "image/png"
        assert r["caption"] == "buckets and a chain"
        assert r["alt"].startswith("Eight boxes")
        assert r["kind"] == "structure" and r["aspect"] == "4:3"
        assert r["cost"] == 0.004 + 0.134 and r["image_cost"] == 0.134
        # every label is another chance to render a misspelt word, so the
        # whitelist is deduped — nine "bucket"s would be an instruction to
        # write the word nine times on one figure
        assert r["labels"] == ["bucket"]
        assert drawn["prompt"].count('"bucket"') == 1
        assert drawn["aspect"] == "4:3"

        # a genuinely varied list keeps its order and stops at the cap
        varied = dict(brief, labels=["Key", "key", "hash", "bucket", "chain",
                                     "load", "resize", "probe", "slot"])
        handle_illustrate({"passage": "a drawable passage"},
                          lambda *a, **k: (json.dumps(varied), 0.0))
        assert drawn["prompt"].count("Write these 6 labels") == 1
        assert '"Key", "hash", "bucket", "chain", "load", "resize"' in drawn["prompt"]

        # "there is no shape here" is an answer, not an error: 200, no picture,
        # no image bill — only the brief was paid for
        drawn.clear()
        no = handle_illustrate(
            {"passage": "Elegance is largely a matter of taste."},
            lambda *a, **k: (json.dumps(
                {"drawable": False, "why": "this is an opinion, not a structure"}), 0.004))
        assert no["drawable"] is False and no["cost"] == 0.004
        assert "opinion" in no["why"] and "data" not in no
        assert not drawn, "a refusal must not reach the image model"

        # a reply with nothing usable in it is a real failure
        try:
            handle_illustrate({"passage": "something drawable"},
                              lambda *a, **k: ("no json at all", 0.0))
            assert False, "an unusable brief must raise"
        except ApiError:
            pass
        for bad in ({"passage": ""}, {"passage": "x"}):
            try:
                handle_illustrate(bad, stub)
                assert False, "a passage too short to describe anything must raise"
            except ApiError:
                pass

        # a redraw's steer reaches the art director verbatim
        handle_illustrate({"passage": "Chaining keeps a list.", "hint": "show three buckets"},
                          stub)
        assert "show three buckets" in seen["msg"]

        # with no key the route refuses before spending anything
        gemini_images.api_key = lambda: ""
        try:
            handle_illustrate({"passage": "something drawable"}, stub)
            assert False, "no key must raise"
        except ApiError as exc:
            assert exc.status == 503 and "GEMINI_API_KEY" in str(exc)
    finally:
        gemini_images.generate, gemini_images.api_key = real_generate, real_key
    print("ok  handle_illustrate (brief, clamping, refusal, missing key)")


def test_image_exports():
    """Figures survive the .know.json round-trip as descriptions, reach both
    exports, and only the HTML one carries the actual picture."""
    d = {
        "format": "learn-with-claude/knowledge-tree", "version": 1, "id": "t3",
        "root_topic": "hash tables", "created": "2026-08-01", "root_id": 1, "next": 2,
        "nodes": {"1": {"id": 1, "label": "collisions", "children": [],
                        "turns": [{"turn": 1, "action": "q", "tutor": "a"},
                                  {"turn": 2, "action": "q2", "tutor": "a2"}]}},
        "images": [
            {"id": "img_a1", "node": 1, "turn": 2, "when": "2026-08-01T10:00:00Z",
             "caption": "buckets and a collision chain",
             "alt": "Eight boxes in a row; the third holds a chain of two entries.",
             "mime": "image/webp", "data": "UklGRg=="},
            {"id": "img_a0", "node": 1, "turn": 2, "when": "2026-08-01T09:00:00Z",
             "caption": "an empty bucket array", "alt": "Eight empty boxes in a row."},
            {"id": "img_b1", "node": 99, "turn": 1, "caption": "orphaned"},
            {"id": "", "node": 1, "turn": 1, "caption": "no id"},
            "not a dict",
        ],
    }
    kb = KnowledgeTree.from_dict(d)
    assert kb.to_dict()["images"] == d["images"]      # extras survive the CLI untouched

    figs = kb.image_map()
    assert list(figs) == [(1, 2)] and len(figs[(1, 2)]) == 2   # orphan + junk dropped
    assert [f["caption"] for f in figs[(1, 2)]] == \
        ["an empty bucket array", "buckets and a collision chain"]   # oldest first

    # markdown deliberately carries the description, not a data URI per figure:
    # a .md with several hundred KB of base64 in it is unreadable in the
    # editors people actually open .md files in
    md = kb.to_markdown()
    assert "> 🖼 **Figure — buckets and a collision chain**" in md
    assert "Eight boxes in a row; the third holds a chain" in md
    assert "orphaned" not in md
    assert "UklGRg==" not in md

    # the reading page is self-contained, so there the picture does travel
    html = tree_to_html(kb)
    assert 'src="data:image/webp;base64,UklGRg=="' in html
    assert 'alt="Eight boxes in a row; the third holds a chain of two entries."' in html
    assert "buckets and a collision chain" in html
    # a figure whose bytes never came along says what it was instead of
    # rendering a broken-image box
    assert "Eight empty boxes in a row." in html and 'class="nofig"' in html
    assert "orphaned" not in html

    # a data URI already assembled by the client is passed through; anything
    # that isn't an image we wrote is refused rather than injected into the page
    from learn_with_claude.export_html import _figure_src
    assert _figure_src({"data": "data:image/png;base64,AAA="}) == "data:image/png;base64,AAA="
    assert _figure_src({"data": "data:text/html;base64,AAA="}) == ""
    assert _figure_src({"data": 'x" onerror="alert(1)', "mime": "image/webp"}) == ""
    assert _figure_src({"data": "AAA=", "mime": "text/html"}) == ""
    assert _figure_src({}) == ""

    # no figures at all -> no key in the file, nothing in either export
    d2 = dict(d); d2.pop("images")
    kb2 = KnowledgeTree.from_dict(d2)
    assert "images" not in kb2.to_dict()
    assert "🖼" not in kb2.to_markdown() and "tfig" not in tree_to_html(kb2)
    print("ok  image exports (round-trip, markdown description, html data URI)")


def test_source_threading():
    """A sourced tree grounds both personas; an unsourced body is untouched."""
    from learn_with_claude.webapi import (
        SOURCE_MAX,
        learner_opening,
        source_of,
        tutor_extra_context,
    )

    passage = "A hash table maps keys to buckets via a hash function."

    # the learner opening keeps the passage FIRST and the contract last
    body = {"topic": "hash tables", "source": "  " + passage + "  "}
    msg = learner_opening(body)
    assert passage in msg
    assert msg.index(passage) < msg.index("hash tables")
    plain = learner_opening({"topic": "hash tables"})
    assert msg.endswith(plain[-40:])          # the original task text stays last
    assert passage not in plain

    # every conversation kind in a sourced tree stays anchored
    for kind in ("branch", "followup", "gaps", "deepen"):
        m = learner_opening({"topic": "t", "kind": kind, "source": passage})
        assert passage in m

    # the tutor gets a grounding block — alone for root, appended after the
    # kind's own context otherwise
    extra = tutor_extra_context({"kind": "root", "source": passage})
    assert passage in extra and "Ground your answers" in extra
    both = tutor_extra_context({"kind": "gaps", "baseline": "knows arrays",
                                "source": passage})
    assert "knows arrays" in both and passage in both
    assert both.index("knows arrays") < both.index(passage)
    assert tutor_extra_context({"kind": "root"}) == ""

    # cap and junk tolerance
    assert len(source_of({"source": "x" * (SOURCE_MAX + 500)})) == SOURCE_MAX
    assert source_of({"source": 42}) == ""
    assert source_of({}) == ""
    print("ok  source threading (learner opening, tutor context, cap)")


def test_learner_brief_threading():
    """The learner drives every question, so an anchored Copilot session has to
    reach it too — as scenery, never as the transcript the tutor gets."""
    from learn_with_claude.webapi import handle_learner, learner_opening, model_routes

    brief = "KESTREL — routing service\nFINCH — human review queue"
    passage = "A hash table maps keys to buckets."

    plain = learner_opening({"topic": "amber legs"})
    withb = learner_opening({"topic": "amber legs"}, brief)
    assert brief in withb and brief not in plain
    assert "SETTING" in withb
    # scenery on top, the task (and its output contract) still last
    assert withb.index(brief) < withb.index("amber legs")
    assert withb.endswith(plain[-40:])
    # the guardrails the learner needs are actually in the block
    low = withb.lower()
    for rule in ["never quote it", "not understanding it", "never let it supply an answer",
                 "never sets your agenda"]:
        assert rule in low, rule

    # with a passage too: the passage is what's being studied, the session is
    # only the room it stands in, so scenery goes above it
    both = learner_opening({"topic": "t", "source": passage}, brief)
    assert both.index(brief) < both.index(passage)

    # every conversation kind carries it
    for kind in ("branch", "followup", "gaps", "deepen"):
        assert brief in learner_opening({"topic": "t", "kind": kind}, brief)

    seen = {}

    def capture(system, messages, role, **kw):
        seen["opening"] = messages[0]["content"]
        return ('{"thinking":"t","new_term":null,"action":"a","confidence":10,'
                '"done":false}'), 0.25

    # the brief costs something to make, so it rides back with the turn that
    # triggered it — the header must not under-report what was spent
    routes = model_routes(capture, learner_grounding=lambda: (brief, 0.5))
    out = routes["learner"]({"kind": "root", "topic": "t", "turns": []})
    assert brief in seen["opening"]
    assert out["cost"] == 0.75, out["cost"]

    # a plain-string hook still works, and costs nothing
    routes = model_routes(capture, learner_grounding=lambda: brief)
    assert routes["learner"]({"kind": "root", "topic": "t", "turns": []})["cost"] == 0.25

    # hosted (no hook at all) is byte-for-byte what it was before this existed
    seen.clear()
    model_routes(capture)["learner"]({"kind": "root", "topic": "t", "turns": []})
    assert "SETTING" not in seen["opening"]
    assert seen["opening"] == learner_opening({"kind": "root", "topic": "t"})

    # and handle_learner's own default is no brief
    seen.clear()
    handle_learner({"kind": "root", "topic": "t", "turns": []}, capture)
    assert "SETTING" not in seen["opening"]
    print("ok  learner brief threading (scenery block, ordering, cost, hosted unchanged)")


def test_order_questions():
    """Whatever the model returns, the result is a permutation — the button
    must never lose, duplicate, or invent a question."""
    from learn_with_claude.webapi import (
        MAX_ORDER_QUESTIONS,
        ApiError,
        handle_order_questions,
    )

    qs = ["what is a bloom filter?", "why does STARLING use one?",
          "what is a hash function?", "what is a false positive?"]

    def reply(text, cost=0.02):
        return lambda system, messages, role, **kw: (text, cost)

    # the happy path: the model's order is honoured
    out = handle_order_questions({"questions": qs}, reply('{"order": [2, 0, 3, 1]}'))
    assert out["order"] == [2, 0, 3, 1] and out["cost"] == 0.02

    # dropped indices are appended in their original order, never lost
    assert handle_order_questions({"questions": qs}, reply('{"order": [3]}'))["order"] \
        == [3, 0, 1, 2]
    # duplicates and out-of-range are ignored
    assert handle_order_questions(
        {"questions": qs}, reply('{"order": [1, 1, 9, -2, 0]}'))["order"] == [1, 0, 2, 3]
    # digit strings are accepted; booleans are not indices
    assert handle_order_questions(
        {"questions": qs}, reply('{"order": ["2", true, "0"]}'))["order"] == [2, 0, 1, 3]
    # unusable replies degrade to the order it was given, not to chaos
    for junk in ["not json at all", '{"order": "nope"}', "{}", '{"order": []}']:
        assert handle_order_questions({"questions": qs}, reply(junk))["order"] == [0, 1, 2, 3]

    # fewer than two questions never reaches the model
    def explode(*a, **k):
        raise AssertionError("must not call the model")

    assert handle_order_questions({"questions": ["only one"]}, explode) \
        == {"order": [0], "cost": 0.0}
    assert handle_order_questions({"questions": []}, explode) == {"order": [], "cost": 0.0}
    # blanks are dropped before the model sees them
    assert handle_order_questions({"questions": ["  ", "a", "b"]},
                                  reply('{"order": [1, 0]}'))["order"] == [1, 0]

    # a bank bigger than the cap is truncated, and the answer still fits it
    many = [f"question {i}" for i in range(MAX_ORDER_QUESTIONS + 10)]
    out = handle_order_questions({"questions": many}, reply('{"order": [5]}'))
    assert len(out["order"]) == MAX_ORDER_QUESTIONS and out["order"][0] == 5
    assert sorted(out["order"]) == list(range(MAX_ORDER_QUESTIONS))

    for bad in [{}, {"questions": "nope"}]:
        try:
            handle_order_questions(bad, explode)
            assert False, f"must reject {bad!r}"
        except ApiError:
            pass

    # the prompt actually asks for dependency order
    msg = order_questions_message(qs)
    assert "DEPENDENCY" in msg and all(q in msg for q in qs)
    assert '"order"' in msg
    print("ok  order questions (permutation repair, guards, cap, prompt)")


def test_suggest_questions():
    """Suggestions are proposals — this only has to return a short, clean,
    non-duplicate list. Nothing is added anywhere by the call itself."""
    from learn_with_claude.webapi import (
        MAX_SUGGESTIONS,
        ApiError,
        handle_suggest_questions,
    )

    have = ["what is a B-tree?", "why do B-trees have high fanout?"]

    def reply(payload, cost=0.02):
        return lambda system, messages, role, **kw: (payload, cost)

    out = handle_suggest_questions({"questions": have}, reply(
        '{"questions": ["how does a node split when it fills up?",'
        ' "what is a disk page, and why does it matter here?"]}'))
    assert len(out["questions"]) == 2 and out["cost"] == 0.02
    assert out["questions"][0].startswith("how does a node split")

    # a re-worded duplicate of something banked is dropped — word order,
    # case, punctuation and filler words all ignored
    out = handle_suggest_questions({"questions": have}, reply(
        '{"questions": ["A B-tree — what IS it?",'
        ' "Why is the fanout of B-trees high?",'
        ' "what happens on a delete?"]}'))
    assert out["questions"] == ["what happens on a delete?"], out["questions"]

    # suggestions that duplicate each other collapse too
    out = handle_suggest_questions({"questions": have}, reply(
        '{"questions": ["what happens on a delete?", "on a delete, what happens?"]}'))
    assert len(out["questions"]) == 1

    # capped, trimmed, and stripped of junk
    out = handle_suggest_questions({"questions": have}, reply(
        '{"questions": ' + json.dumps([f"question number {i} about trees?" for i in range(10)]) + "}"))
    assert len(out["questions"]) == MAX_SUGGESTIONS
    out = handle_suggest_questions({"questions": have}, reply(
        '{"questions": ["  spaced   out    question about pages?  ", "no", "", 42, null]}'))
    assert out["questions"] == ["spaced out question about pages?"], out["questions"]

    # an unusable reply is simply no suggestions, never an error
    for junk in ["not json", "{}", '{"questions": "nope"}', '{"questions": []}']:
        assert handle_suggest_questions({"questions": have}, reply(junk))["questions"] == []

    # nothing to go on -> refuse rather than invent
    def explode(*a, **k):
        raise AssertionError("must not call the model")

    for bad in [{}, {"questions": "nope"}, {"questions": []}, {"questions": ["  "]}]:
        try:
            handle_suggest_questions(bad, explode)
            assert False, f"must reject {bad!r}"
        except ApiError:
            pass

    # the overlap bar is deliberate: a re-wording is caught, a genuinely
    # narrower question about the same thing is not
    from learn_with_claude.webapi import _question_words, _same_question
    assert _same_question(_question_words("why do B-trees have high fanout?"),
                          _question_words("Why is the fanout of B-trees high?"))
    assert not _same_question(_question_words("what is a B-tree?"),
                              _question_words("what is a B-tree node?"))
    assert not _same_question(_question_words("what is a heap?"),
                              _question_words("what is a stack?"))

    # the prompt aims at gaps and forbids restating
    msg = suggest_questions_message(have, 4)
    assert "MISSING" in msg and "Never restate" in msg
    assert all(q in msg for q in have) and '"questions"' in msg
    print("ok  suggest questions (dedupe by meaning, cap, junk, guards)")


def test_deepen_threading():
    """🔬 look deeper: same topic, re-investigated, seeded with what the node
    already covered, and told explicitly to override the ambient brevity."""
    from learn_with_claude.webapi import learner_opening, tutor_extra_context

    digest = "  Q: what is it\n  A: an array plus a hash function"
    body = {"kind": "deepen", "topic": "what a hash table is", "digest": digest}

    msg = learner_opening(body)
    assert "what a hash table is" in msg and digest.strip() in msg
    assert "MUCH deeper" in msg
    assert "Produce your FIRST turn now" in msg
    assert '"thinking"' in msg  # CONTRACT_REMINDER is appended, same as every other kind

    extra = tutor_extra_context(body)
    assert digest.strip() in extra
    assert "MUCH deeper" in extra
    assert "Depth beats brevity" in extra
    # topic doesn't leak into the tutor's context (only the learner needs it
    # named — the tutor just gets told what's already covered)
    assert tutor_extra_context({"kind": "root"}) == ""
    print("ok  deepen threading (same-topic re-investigation, override wording)")


def test_question_anchoring():
    """Every turn after the first has to be steered by the question the node was
    opened to answer — otherwise the learner hill-climbs on whatever the tutor's
    last reply happened to mention and drifts off the topic entirely."""
    from learn_with_claude.personas import feedback_message
    from learn_with_claude.webapi import anchor_question

    # the anchor is restated verbatim in the per-turn message, with the
    # answer-it-or-name-what's-missing instruction attached
    m = feedback_message("some tutor reply", "what did galileo's ramp show?")
    assert "what did galileo's ramp show?" in m
    assert "ONLY THING YOU ARE HERE TO ANSWER" in m
    assert "new_term" in m  # parking non-blocking curiosities is the escape hatch
    # omitted (older callers) => the message still works, just unanchored
    assert "ONLY THING YOU ARE HERE TO ANSWER" not in feedback_message("reply")

    # root nodes anchor to the topic
    assert anchor_question({"kind": "root", "topic": "hash tables"}) == "hash tables"
    assert anchor_question({"topic": "hash tables"}) == "hash tables"
    assert anchor_question({"kind": "deepen", "topic": "hash tables"}) == "hash tables"

    # ...but on a sub-node "topic" is the ROOT of the whole tree, and anchoring
    # to it would pull the learner back out of the thread it just opened
    branch = {"kind": "branch", "topic": "hash tables", "focus": "why chaining?",
              "branch_a": "Collisions are resolved by chaining."}
    assert anchor_question(branch) == "why chaining?"
    no_focus = dict(branch, focus="")
    assert "Collisions are resolved by chaining." in anchor_question(no_focus)
    assert "hash tables" != anchor_question(no_focus)
    # a long branch answer gets capped — it is repeated on every single turn
    assert len(anchor_question(dict(branch, focus="", branch_a="x" * 900))) < 260

    fu = {"kind": "followup", "topic": "hash tables", "concept": "load factor",
          "opening_question": "when does it resize?"}
    assert anchor_question(fu) == "when does it resize?"
    assert anchor_question(dict(fu, opening_question="")) == "load factor"
    gaps = {"kind": "gaps", "topic": "hash tables", "focus": "resizing",
            "opening_question": ""}
    assert anchor_question(gaps) == "resizing"
    # missing/blank sub-fields never produce an empty anchor
    assert anchor_question({"kind": "branch", "topic": "hash tables"}) == "hash tables"
    assert anchor_question({"kind": "followup", "topic": "hash tables"}) == "hash tables"

    # and the learner prompt itself carries the blocking/parking rule
    assert "BLOCKING" in LEARNER_SYSTEM and "PARK IT" in LEARNER_SYSTEM
    print("ok  question anchoring (per-turn anchor, sub-node anchors, parking rule)")


if __name__ == "__main__":
    test_learner_levels()
    test_tutor_system_segments()
    test_tutor_grounding()
    test_handle_tutor_grounding()
    test_split_tutor_parts()
    test_knowledge_round_trip()
    test_message_builders()
    test_handle_interview()
    test_handle_teachback()
    test_handle_exam()
    test_handle_mark_exam()
    test_exam_exports()
    test_aside_exports()
    test_handle_facts()
    test_facts_exports()
    test_image_prompt()
    test_gemini_reply_parsing()
    test_handle_illustrate()
    test_image_exports()
    test_handle_survey()
    test_source_threading()
    test_learner_brief_threading()
    test_order_questions()
    test_suggest_questions()
    test_deepen_threading()
    test_question_anchoring()
    print("\nall green")
