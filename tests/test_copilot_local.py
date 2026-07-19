"""Plain-python regression tests for the local Copilot mode.

Run with:  python tests/test_copilot_local.py
(no test framework, no model calls — the copilot CLI is stubbed out)
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learn_with_claude import copilot_backend  # noqa: E402
from learn_with_claude.copilot_backend import _parse_stream, compose_prompt  # noqa: E402
from learn_with_claude.localweb import TreeStore, TutorStore  # noqa: E402
from learn_with_claude.webapi import ApiError  # noqa: E402

# A stand-in copilot: prints one assistant.message whose content is the argv
# it was called with (as JSON), plus a result event with a fractional cost.
STUB = """
import json, sys
print(json.dumps({"type": "assistant.message",
                  "data": {"content": json.dumps(sys.argv[1:])}}))
print(json.dumps({"type": "result", "usage": {"premiumRequests": 0.5}}))
"""


def stub_call(monkey_dir, *call_args, **call_kwargs):
    """Run call_model against the stub; returns (argv_list, cost)."""
    stub = Path(monkey_dir) / "stub_copilot.py"
    stub.write_text(STUB, encoding="utf-8")
    real = copilot_backend.COPILOT_CMD
    copilot_backend.COPILOT_CMD = [sys.executable, str(stub)]
    try:
        text, cost = copilot_backend.call_model(*call_args, **call_kwargs)
    finally:
        copilot_backend.COPILOT_CMD = real
    return json.loads(text), cost


def test_compose_prompt():
    p = compose_prompt("SYS RULES", [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "user", "content": "again"},
    ])
    assert "SYS RULES" in p and "[user]:\nhello" in p and "[assistant]:\nhi" in p
    assert p.index("SYSTEM INSTRUCTIONS") < p.index("CONVERSATION") < p.index("YOUR TASK")
    print("ok  compose_prompt")


def test_parse_stream():
    lines = [
        json.dumps({"type": "assistant.message", "data": {"content": "Let me look..."}}),
        "not json at all",
        json.dumps({"type": "assistant.message", "data": {"content": "The answer."}}),
        json.dumps({"type": "result", "usage": {"premiumRequests": 0.33}}),
    ]
    text, cost = _parse_stream("\n".join(lines))
    assert text == "The answer."       # last message wins — narration dropped
    assert cost == 0.33
    try:
        _parse_stream(json.dumps({"type": "result", "usage": {}}))
        assert False, "empty stream must raise"
    except ApiError:
        pass
    print("ok  parse_stream (final message, cost, empty)")


def test_tool_policy():
    with tempfile.TemporaryDirectory() as d:
        msgs = [{"role": "user", "content": "q"}]
        argv, cost = stub_call(d, "sys", msgs, "tutor")
        assert cost == 0.5
        assert "--available-tools=view,grep,glob" in argv
        assert "--allow-all-paths" in argv and "--allow-tool=view" in argv
        assert "--disable-builtin-mcps" in argv and "--no-custom-instructions" in argv

        argv, _ = stub_call(d, "sys", msgs, "learner")
        assert "--available-tools=none" in argv
        assert "--allow-all-paths" not in argv

        # glossary's "none" effort means: no --effort flag at all
        argv, _ = stub_call(d, "sys", msgs, "glossary", effort="none")
        assert "--effort" not in argv
    print("ok  per-role tool policy")


def test_overflow_prompt():
    with tempfile.TemporaryDirectory() as d:
        big = [{"role": "user", "content": "x" * (copilot_backend.ARGV_PROMPT_LIMIT + 100)}]
        argv, _ = stub_call(d, "sys", big, "learner")
        prompt = argv[argv.index("-p") + 1]
        assert "view tool" in prompt and len(prompt) < 500   # bootstrap, not the payload
        assert "--available-tools=view" in argv and "--add-dir" in argv
    print("ok  oversized prompt travels via temp file")


def test_tree_store():
    with tempfile.TemporaryDirectory() as d:
        store = TreeStore(Path(d))
        tree = {"format": "learn-with-claude/knowledge-tree", "version": 1,
                "id": "abc123", "root_topic": "how DNS works", "root_id": 1,
                "nodes": {}, "quiz": {"questions": [1, 2, 3]}}
        assert store.put(tree) == {"ok": True, "rev": 1}
        assert (Path(d) / "how-dns-works.know.json").is_file()   # CLI naming
        assert store.get("abc123")["quiz"] == tree["quiz"]        # verbatim
        # same topic, different id -> new file, not an overwrite
        store.put({**tree, "id": "def456"})
        assert (Path(d) / "how-dns-works-2.know.json").is_file()
        live = [t for t in store.list() if not t["deleted"]]
        assert {t["id"] for t in live} == {"abc123", "def456"}
        # legacy re-put (no base_rev) overwrites in place and bumps the rev
        assert store.put({**tree, "extra": 1})["rev"] == 2
        assert len([t for t in store.list() if not t["deleted"]]) == 2
        # delete leaves a tombstone so other devices see the deletion
        store.delete("abc123")
        listed = {t["id"]: t for t in store.list()}
        assert not listed["def456"]["deleted"]
        assert listed["abc123"]["deleted"] and listed["abc123"]["rev"] == 3
        assert store.get("abc123") is None
        try:
            store.put({"format": "wrong", "id": "abc123"})
            assert False, "bad format must raise"
        except ApiError:
            pass
    print("ok  tree store (naming, verbatim, collisions, tombstones)")


def test_tree_store_revs():
    with tempfile.TemporaryDirectory() as d:
        store = TreeStore(Path(d))
        tree = {"format": "learn-with-claude/knowledge-tree", "version": 1,
                "id": "abc123", "root_topic": "revs", "root_id": 1, "nodes": {}}
        assert store.put(tree, 0) == {"ok": True, "rev": 1}
        # stale base -> conflict carrying the current server copy
        r = store.put({**tree, "mine": 1}, 0)
        assert "conflict" in r and r["conflict"]["rev"] == 1
        assert r["conflict"]["tree"]["id"] == "abc123"
        # matching base -> accepted, rev bumps, the stored doc carries it
        assert store.put({**tree, "mine": 2}, 1) == {"ok": True, "rev": 2}
        assert store.get("abc123")["rev"] == 2
        # a CLI rewrite drops the rev stamp -> rev derives from the file
        # mtime, which is far larger, so clients pull and merge the change
        path = Path(d) / "revs.know.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        del doc["rev"]
        path.write_text(json.dumps(doc), encoding="utf-8")
        derived = next(t["rev"] for t in store.list() if t["id"] == "abc123")
        assert derived > 2
        r = store.put({**tree, "mine": 3}, 2)
        assert "conflict" in r and r["conflict"]["rev"] == derived
        # deleted elsewhere: an edit based on any old rev loses...
        store.delete("abc123")
        r = store.put({**tree, "mine": 4}, derived)
        assert r["conflict"].get("deleted") is True
        # ...but an explicit create (base 0) resurrects the tree
        r = store.put({**tree, "mine": 5}, 0)
        assert r["ok"] and r["rev"] > derived
        assert not next(t for t in store.list() if t["id"] == "abc123")["deleted"]
    print("ok  tree store rev protocol (CAS, mtime fallback, tombstone rules)")


def test_tutor_store():
    with tempfile.TemporaryDirectory() as d:
        store = TutorStore(Path(d) / "tutors.json")
        assert store.get() is None
        doc = {"saved_at": "2026-07-18", "tutors": [
            {"id": "socratic", "name": "Socratic", "style": "Only questions."}]}
        store.put(doc)
        assert store.get() == doc
        for bad in [None, {"tutors": "nope"},
                    {"tutors": [{"id": "BAD ID", "name": "x", "style": "y"}]},
                    {"tutors": [{"id": "a", "name": "", "style": "y"}]}]:
            try:
                store.put(bad)
                assert False, f"must reject {bad!r}"
            except ApiError:
                pass
    print("ok  tutor store (round-trip, validation)")


if __name__ == "__main__":
    test_compose_prompt()
    test_parse_stream()
    test_tool_policy()
    test_overflow_prompt()
    test_tree_store()
    test_tree_store_revs()
    test_tutor_store()
    print("\nall green")
