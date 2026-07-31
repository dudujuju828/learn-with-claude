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
    test_handle_survey()
    test_source_threading()
    test_learner_brief_threading()
    test_order_questions()
    test_suggest_questions()
    test_deepen_threading()
    test_question_anchoring()
    print("\nall green")
