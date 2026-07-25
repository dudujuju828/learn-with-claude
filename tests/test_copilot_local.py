"""Plain-python regression tests for the local Copilot mode.

Run with:  python tests/test_copilot_local.py
(no test framework, no model calls — the copilot CLI is stubbed out)
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learn_with_claude import copilot_backend, local_settings  # noqa: E402
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


def test_local_settings_sanitize():
    # lenient (load) path: garbage is silently dropped, never raises
    d = local_settings.sanitize({
        "effort": "wat", "models": "nope",
        "mcp_servers": [{"name": "BAD NAME"}, {"name": "ok", "transport": "stdio"}],
    })
    assert d["effort"] == "" and d["models"] == {"learner": "", "tutor": "", "glossary": ""}
    assert d["mcp_servers"] == []   # bad name dropped; "ok" has no command -> dropped too

    with tempfile.TemporaryDirectory() as td:
        d2 = local_settings.sanitize({"code_dir": td, "models": {"tutor": "gpt-5.4"}})
        assert d2["code_dir"] == str(Path(td).resolve())
        assert d2["models"]["tutor"] == "gpt-5.4"
    assert local_settings.sanitize({"code_dir": "C:/not/a/real/path/xyz"})["code_dir"] == ""

    # strict (save) path: raises with a message fit to show the person who typed it
    for bad, needle in [
        ({"effort": "extreme"}, "effort"),
        ({"code_dir": "C:/definitely/not/a/real/path/xyz"}, "not a directory"),
        ({"mcp_servers": [{"name": "Bad Name"}]}, "lowercase"),
        ({"mcp_servers": [{"name": "srv", "transport": "http"}]}, "url"),
        ({"mcp_servers": [{"name": "srv", "transport": "stdio"}]}, "command"),
        ({"mcp_servers": [{"name": "srv", "transport": "http", "url": "https://a"},
                          {"name": "srv", "transport": "http", "url": "https://b"}]}, "duplicate"),
        ({"mcp_servers": [{"name": f"s{i}", "transport": "http", "url": "https://x"}
                          for i in range(local_settings.MAX_SERVERS + 1)]}, "at most"),
    ]:
        try:
            local_settings.sanitize(bad, strict=True)
            assert False, f"must reject {bad!r}"
        except ValueError as e:
            assert needle in str(e), f"{needle!r} not in {e}"

    # a valid stdio server and the Confluence preset both round-trip
    good = local_settings.sanitize({"mcp_servers": [
        {"name": "files", "transport": "stdio", "command": "npx",
         "args": ["-y", "thing"], "enabled": True, "note": "x"},
        {**local_settings.CONFLUENCE_PRESET, "enabled": True},
    ]}, strict=True)
    assert [s["name"] for s in good["mcp_servers"]] == ["files", "confluence"]
    assert good["mcp_servers"][0]["args"] == ["-y", "thing"]
    assert good["mcp_servers"][1]["url"] == local_settings.CONFLUENCE_PRESET["url"]
    print("ok  local_settings.sanitize (lenient load vs strict save)")


def test_local_settings_store():
    with tempfile.TemporaryDirectory() as d:
        store = local_settings.LocalSettingsStore(Path(d) / "local_settings.json")
        assert store.load() == local_settings.default()   # no file yet
        saved = store.save({"effort": "high", "models": {"tutor": "gpt-5.4"}})
        assert saved["effort"] == "high"
        assert store.load() == saved                       # round-trips from disk
        try:
            store.save({"effort": "extreme"})
            assert False, "bad effort must raise"
        except ValueError:
            pass
        assert store.load() == saved                        # rejected save didn't touch the file

        # a corrupted file on disk degrades to defaults, never crashes the server
        store.path.write_text("not json", encoding="utf-8")
        assert store.load() == local_settings.default()
    print("ok  local settings store (round-trip, rejected save, corrupt file)")


def test_copilot_backend_overrides():
    original = copilot_backend._snapshot()
    try:
        with tempfile.TemporaryDirectory() as d:
            settings = local_settings.sanitize({
                "models": {"tutor": "gpt-5.4"}, "effort": "high", "code_dir": d,
                "mcp_servers": [
                    {**local_settings.CONFLUENCE_PRESET, "enabled": True},
                    {"name": "sidelined", "transport": "http", "url": "https://x", "enabled": False},
                ],
            }, strict=True)
            copilot_backend.configure(settings)

            assert copilot_backend.effective_model("tutor") == "gpt-5.4"
            # an untouched role still falls back to the env-derived default
            assert copilot_backend.effective_model("learner") == copilot_backend.ROLE_MODELS["learner"]
            assert copilot_backend.effective_effort() == "high"

            flags, cwd = copilot_backend._role_flags("tutor")
            assert "--available-tools=view,grep,glob,confluence" in flags
            assert "--allow-tool=confluence" in flags
            assert "--allow-tool=sidelined" not in flags   # disabled server excluded entirely
            assert "--add-dir" in flags and d in flags
            i = flags.index("--additional-mcp-config")
            cfg = json.loads(flags[i + 1])
            assert list(cfg["mcpServers"]) == ["confluence"]
            assert cfg["mcpServers"]["confluence"]["url"] == local_settings.CONFLUENCE_PRESET["url"]

            grounding = copilot_backend.grounding_text()
            assert d in grounding and "confluence" in grounding and "sidelined" not in grounding

            # learner/glossary stay tool-free regardless of any of this
            assert copilot_backend._role_flags("learner") == (["--available-tools=none"], None)
    finally:
        copilot_backend.configure(original)
    # settings reset -> the untouched-default flags are exactly what they were before
    argv, _ = stub_call(tempfile.mkdtemp(), "sys", [{"role": "user", "content": "q"}], "tutor")
    assert "--available-tools=view,grep,glob" in argv and "--additional-mcp-config" not in argv
    print("ok  copilot_backend settings overlay (models, effort, code_dir, mcp servers)")


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
    test_local_settings_sanitize()
    test_local_settings_store()
    test_copilot_backend_overrides()
    test_tree_store()
    test_tree_store_revs()
    test_tutor_store()
    print("\nall green")
