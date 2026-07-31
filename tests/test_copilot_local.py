"""Plain-python regression tests for the local Copilot mode.

Run with:  python tests/test_copilot_local.py
(no test framework, no model calls — the copilot CLI is stubbed out)
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from learn_with_claude import copilot_backend, copilot_sessions, local_settings  # noqa: E402
from learn_with_claude.copilot_backend import _parse_stream, compose_prompt  # noqa: E402
from learn_with_claude.localweb import GlobalQuestionStore, TreeStore, TutorStore  # noqa: E402
from learn_with_claude.webapi import ApiError, model_routes  # noqa: E402

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
        assert "--available-tools=view,grep,glob,skill" in argv
        assert "--allow-all-paths" in argv and "--allow-tool=view" in argv
        assert "--allow-tool=skill" in argv
        assert "--disable-builtin-mcps" in argv
        # the tutor keeps AGENTS.md/custom instructions and skills active —
        # it's meant to answer like the operator's own Copilot setup would
        assert "--no-custom-instructions" not in argv

        argv, _ = stub_call(d, "sys", msgs, "learner")
        assert "--available-tools=none" in argv
        assert "--allow-all-paths" not in argv
        # the learner/glossary personas must stay uncontaminated roleplay
        assert "--no-custom-instructions" in argv

        # glossary's "none" effort means: no --effort flag at all
        argv, _ = stub_call(d, "sys", msgs, "glossary", effort="none")
        assert "--effort" not in argv
        assert "--no-custom-instructions" in argv
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
    # lenient (load) path: garbage is silently dropped, never raises. Server
    # entries are just {name, enabled, note} references now — no transport/
    # command/url to validate, since the servers themselves are defined in
    # the Copilot CLI's own config, not here.
    d = local_settings.sanitize({
        "effort": "wat", "models": "nope",
        "mcp_servers": [{"name": "BAD NAME"}, {"name": "ok"}, "not a dict"],
    })
    assert d["effort"] == "" and d["models"] == {"learner": "", "tutor": "", "glossary": ""}
    assert [s["name"] for s in d["mcp_servers"]] == ["ok"]   # bad name / non-dict dropped

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
        ({"mcp_servers": "nope"}, "list"),
        ({"mcp_servers": [{"name": "srv"}, {"name": "srv"}]}, "duplicate"),
        ({"mcp_servers": [{"name": f"s{i}"} for i in range(local_settings.MAX_SERVERS + 1)]}, "at most"),
    ]:
        try:
            local_settings.sanitize(bad, strict=True)
            assert False, f"must reject {bad!r}"
        except ValueError as e:
            assert needle in str(e), f"{needle!r} not in {e}"

    # a valid reference round-trips; enabled defaults true when omitted
    good = local_settings.sanitize({"mcp_servers": [
        {"name": "confluence", "enabled": True, "note": local_settings.CONFLUENCE_PRESET["note"]},
        {"name": "files"},
    ]}, strict=True)
    assert [s["name"] for s in good["mcp_servers"]] == ["confluence", "files"]
    assert good["mcp_servers"][0]["note"] == local_settings.CONFLUENCE_PRESET["note"]
    assert good["mcp_servers"][1]["enabled"] is True
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
                    {"name": "confluence", "enabled": True, "note": local_settings.CONFLUENCE_PRESET["note"]},
                    {"name": "sidelined", "enabled": False},
                ],
            }, strict=True)
            copilot_backend.configure(settings)

            assert copilot_backend.effective_model("tutor") == "gpt-5.4"
            # an untouched role still falls back to the env-derived default
            assert copilot_backend.effective_model("learner") == copilot_backend.ROLE_MODELS["learner"]
            assert copilot_backend.effective_effort() == "high"

            flags, cwd = copilot_backend._role_flags("tutor")
            assert "--available-tools=view,grep,glob,skill,confluence" in flags
            assert "--allow-tool=confluence" in flags
            assert "--allow-tool=sidelined" not in flags   # disabled server excluded entirely
            assert "--add-dir" in flags and d in flags
            # servers are never defined here — they live in the CLI's own
            # ~/.copilot/mcp-config.json, loaded by default with no flag needed
            assert "--additional-mcp-config" not in flags

            grounding = copilot_backend.grounding_text()
            assert d in grounding and "confluence" in grounding and "sidelined" not in grounding

            # learner/glossary stay tool-free and instruction-free regardless
            assert copilot_backend._role_flags("learner") == (
                ["--available-tools=none", "--no-custom-instructions"], None)
    finally:
        copilot_backend.configure(original)
    # settings reset -> the untouched-default flags are exactly what they were before
    argv, _ = stub_call(tempfile.mkdtemp(), "sys", [{"role": "user", "content": "q"}], "tutor")
    assert "--available-tools=view,grep,glob,skill" in argv
    assert "--additional-mcp-config" not in argv
    print("ok  copilot_backend settings overlay (models, effort, code_dir, mcp servers)")


MCP_STUB = """
import json, sys
argv = sys.argv[1:]
if len(argv) >= 2 and argv[0] == "mcp" and argv[1] == "list":
    print(json.dumps({"mcpServers": {
        "confluence": {"type": "http", "url": "https://mcp.atlassian.com/v1/mcp/authv2",
                       "source": "user", "tools": ["*"]},
        "files": {"type": "stdio", "command": "npx", "source": "workspace"},
    }}))
    sys.exit(0)
if len(argv) >= 2 and argv[0] == "mcp" and argv[1] == "add":
    sys.exit(1 if "FAIL" in argv else 0)
sys.exit(1)
"""


def test_mcp_server_discovery_and_registration():
    with tempfile.TemporaryDirectory() as d:
        stub = Path(d) / "mcp_stub.py"
        stub.write_text(MCP_STUB, encoding="utf-8")
        real = copilot_backend.COPILOT_CMD
        copilot_backend.COPILOT_CMD = [sys.executable, str(stub)]
        try:
            servers = copilot_backend.list_global_mcp_servers()
            names = {s["name"] for s in servers}
            assert names == {"confluence", "files"}
            conf = next(s for s in servers if s["name"] == "confluence")
            assert conf["source"] == "user" and conf["type"] == "http"

            copilot_backend.add_global_mcp_server(
                "confluence", transport="http", url="https://mcp.atlassian.com/v1/mcp/authv2")
            try:
                copilot_backend.add_global_mcp_server("confluence", transport="http", url="FAIL")
                assert False, "a nonzero exit must raise ApiError"
            except ApiError:
                pass
        finally:
            copilot_backend.COPILOT_CMD = real

        # a CLI that can't run at all -> empty list, never a crash (the
        # settings panel just shows an empty checklist, nothing to toggle)
        copilot_backend.COPILOT_CMD = [sys.executable, str(Path(d) / "does_not_exist.py")]
        try:
            assert copilot_backend.list_global_mcp_servers() == []
        finally:
            copilot_backend.COPILOT_CMD = real
    print("ok  MCP server discovery + registration (list/add, stubbed CLI)")


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


def test_global_question_store():
    with tempfile.TemporaryDirectory() as d:
        store = GlobalQuestionStore(Path(d) / "global_questions.json")
        assert store.get() is None
        doc = {"saved_at": "2026-07-26", "questions": [
            {"id": "cac7a33b", "text": "why does a hash table resize", "added": "2026-07-26"}]}
        store.put(doc)
        assert store.get() == doc
        # an answered entry (treeId/node/turn added once investigated) round-trips too
        answered = {"saved_at": "2026-07-26", "questions": [
            {"id": "cac7a33b", "text": "why does a hash table resize", "added": "2026-07-26",
             "answered": True, "treeId": "abc123def456", "node": 1, "turn": 1}]}
        store.put(answered)
        assert store.get() == answered
        for bad in [None, {"questions": "nope"},
                    {"questions": [{"id": "BAD ID", "text": "y"}]},
                    {"questions": [{"id": "cac7a33b", "text": ""}]},
                    {"questions": [{"id": f"{i:08x}", "text": "x"} for i in range(301)]}]:
            try:
                store.put(bad)
                assert False, f"must reject {bad!r}"
            except ApiError:
                pass
    print("ok  global question store (round-trip, answered fields, validation)")


def _fake_session(root: Path, session_id: str, exchanges, *, noise=True,
                  name=None, cwd=r"C:\work\thing"):
    """Write a session-state dir the way the Copilot CLI lays one out.

    `name` mirrors what /rename does: it sets the name AND flips user_named.
    Without it the CLI still writes a name — the first prompt, as a block
    scalar — which is exactly what must NOT count as a name here.
    """
    d = root / session_id
    d.mkdir(parents=True, exist_ok=True)
    auto = (exchanges[0][0] if exchanges else "").splitlines() or [""]
    ws = [f"id: {session_id}", f"cwd: {cwd}", "client_name: github/cli"]
    if name is None:
        ws.append("name: |-")
        ws += [f"  {line}" for line in auto]
        ws.append("user_named: false")
    else:
        ws += [f"name: {name}", "user_named: true"]
    ws += ["summary_count: 0", "created_at: 2026-07-30T09:00:00.000Z",
           "updated_at: 2026-07-30T09:30:00.000Z"]
    (d / "workspace.yaml").write_text("\n".join(ws) + "\n", encoding="utf-8")
    lines = []
    if noise:   # the events a real session is mostly made of, all ignorable
        lines.append({"type": "session.info", "data": {"message": "configuration"}})
        lines.append({"type": "assistant.reasoning", "data": {"reasoningId": "opaque"}})
    for user, assistant in exchanges:
        lines.append({"type": "user.message",
                      "data": {"content": user,
                               "transformedContent": "<current_datetime/>\n" + user}})
        if noise:   # a turn where the assistant only called a tool says nothing
            lines.append({"type": "assistant.message",
                          "data": {"content": "", "toolRequests": [{"name": "view"}]}})
        lines.append({"type": "assistant.message", "data": {"content": assistant}})
    (d / "events.jsonl").write_text(
        "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return d


def test_session_reading():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            root = home / "session-state"
            _fake_session(root, "abc12345-1111-2222-3333-444455556666",
                          [("how does the parser handle nested quotes?",
                            "it re-enters the scanner with a depth counter"),
                           ("and on EOF?", "it raises Unterminated")])
            # this app's own calls must never show up in the picker
            _fake_session(root, "dddddddd-0000-0000-0000-000000000000",
                          [("=== SYSTEM INSTRUCTIONS (these govern your reply) ===\nYou are a tutor",
                            "a hash table maps keys to slots")])
            (root / "eeeeeeee-0000-0000-0000-000000000000").mkdir(parents=True)  # no events

            msgs = copilot_sessions._messages(
                root / "abc12345-1111-2222-3333-444455556666" / "events.jsonl")
            assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"], msgs
            assert "<current_datetime" not in msgs[0]["text"]     # the clean content, not the CLI's
            assert all(m["text"] for m in msgs)                   # tool-only turns dropped

            assert copilot_sessions.resolve("abc12345") == "abc12345-1111-2222-3333-444455556666"
            assert copilot_sessions.resolve("abc12345-1111-2222-3333-444455556666")
            assert copilot_sessions.resolve("nope") is None
            assert copilot_sessions.resolve("") is None
            assert copilot_sessions.resolve("../../etc") is None   # not an id shape
            assert copilot_sessions.resolve("eeeeeeee") is None    # no transcript to read

            ids = [s["id"][:8] for s in copilot_sessions.recent()]
            assert ids == ["abc12345"], ids      # own-call + empty sessions filtered out

            info = copilot_sessions.describe("abc12345-1111-2222-3333-444455556666")
            assert info["messages"] == 4
            assert info["title"].startswith("how does the parser")
            assert copilot_sessions.describe("nosuch") is None

            t = copilot_sessions.transcript("abc12345-1111-2222-3333-444455556666")
            assert "[user]" in t and "nested quotes" in t and "Unterminated" in t

            # a long session is handed over WHOLE by default — anchoring a
            # session to study it, only to get an abridgement, is the one
            # thing this must not do
            _fake_session(root, "ffffffff-0000-0000-0000-000000000000",
                          [(f"question {i} " + "x" * 400, f"answer {i} " + "y" * 400)
                           for i in range(40)], noise=False)
            whole = copilot_sessions.transcript("ffffffff-0000-0000-0000-000000000000")
            assert len(whole) > 32000, len(whole)
            assert "messages omitted" not in whole
            for i in range(40):     # every single exchange survives, in order
                assert f"question {i} " in whole and f"answer {i} " in whole
            # a message is never chopped mid-way either
            assert ("x" * 400) in whole and ("y" * 400) in whole

            # an explicit cap (LEARN_SESSION_MEMORY_MAX) still works, and when
            # it bites it keeps the opening and the tail and says so
            capped = copilot_sessions.transcript("ffffffff-0000-0000-0000-000000000000",
                                                 budget=6000)
            assert len(capped) <= 6000, len(capped)
            assert "question 0" in capped and "messages omitted" in capped
            assert "answer 39" in capped and "question 20" not in capped

            # describe() reports the real extent, so nothing is hidden
            info = copilot_sessions.describe("ffffffff-0000-0000-0000-000000000000")
            assert info["chars"] > 32000 and info["trimmed"] is False, info
        finally:
            os.environ.pop("COPILOT_HOME", None)
    print("ok  copilot session reading (parse, resolve, filter, budget)")


def test_session_names():
    """/rename is the one handle you can get without leaving the session, so
    a named session has to be usable by that name."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            root = home / "session-state"
            named = "11111111-aaaa-bbbb-cccc-dddddddddddd"
            plain = "22222222-aaaa-bbbb-cccc-dddddddddddd"
            _fake_session(root, named, [("how does the scheduler back off?", "exponentially")],
                          name="parser-work", cwd=r"C:\work\compiler")
            _fake_session(root, plain, [("unrelated question", "unrelated answer")])

            ws = copilot_sessions._workspace(named)
            assert ws["id"] == named and ws["user_named"] is True     # bools, not strings
            assert ws["cwd"] == r"C:\work\compiler"

            assert copilot_sessions._label(named) == ("parser-work", r"C:\work\compiler")
            # an auto-generated name is the first prompt, and must not count
            assert copilot_sessions._label(plain)[0] == ""

            assert copilot_sessions.resolve("parser-work") == named
            assert copilot_sessions.resolve("PARSER-WORK") == named   # case-insensitive
            assert copilot_sessions.resolve("parser") is None         # exact only, like the CLI
            assert copilot_sessions.resolve("11111111") == named      # id prefix still works
            assert copilot_sessions.resolve("unrelated question") is None

            # a name gets saved as the *id*, so renaming later can't break it
            clean = local_settings.sanitize({"tutor_session": "parser-work"}, strict=True)
            assert clean["tutor_session"] == named, clean

            info = copilot_sessions.describe(named)
            assert info["name"] == "parser-work" and info["cwd"] == r"C:\work\compiler"
            assert copilot_sessions.describe(plain)["name"] == ""

            # an ambiguous id prefix is refused rather than guessed
            _fake_session(root, "11111111-eeee-ffff-0000-111111111111", [("q", "a")])
            assert copilot_sessions.resolve("11111111") is None
        finally:
            os.environ.pop("COPILOT_HOME", None)
    print("ok  session names (/rename), cwd labels, ambiguous prefixes")


def test_session_memory_tracks_a_live_session():
    """The CLI flushes each turn as it happens, so an anchored session that is
    still running must be picked up as it grows — not frozen at first read."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            sid = "33333333-aaaa-bbbb-cccc-dddddddddddd"
            root = home / "session-state"
            _fake_session(root, sid, [("what's the retry policy?", "three attempts")],
                          noise=False)
            copilot_backend.configure(
                local_settings.sanitize({"tutor_session": sid}, strict=True))
            copilot_backend._memory_cache["stamp"] = None
            assert "three attempts" in copilot_backend.grounding_text()

            # the session keeps going in another terminal
            events = (root / sid / "events.jsonl")
            events.write_text(
                events.read_text(encoding="utf-8") +
                json.dumps({"type": "user.message", "data": {"content": "and after that?"}}) + "\n" +
                json.dumps({"type": "assistant.message",
                            "data": {"content": "it lands in the DLQ called HALIBUT"}}) + "\n",
                encoding="utf-8")

            grounding = copilot_backend.grounding_text()
            assert "HALIBUT" in grounding, "a growing session must be re-read"
            assert "three attempts" in grounding
        finally:
            os.environ.pop("COPILOT_HOME", None)
            copilot_backend.configure(local_settings.default())
            copilot_backend._memory_cache["stamp"] = None
    print("ok  memory keeps up with a session that's still running")


def test_tutor_session_setting():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            sid = "abc12345-1111-2222-3333-444455556666"
            _fake_session(home / "session-state", sid,
                          [("what does the retry budget do?",
                            "it caps redeliveries at five per partition")])

            # a pasted prefix is resolved to the full id on save
            clean = local_settings.sanitize({"tutor_session": "abc123"}, strict=True)
            assert clean["tutor_session"] == sid, clean

            for bad in ["ffffffff", "not a hash!"]:
                try:
                    local_settings.sanitize({"tutor_session": bad}, strict=True)
                    assert False, f"must reject {bad!r}"
                except ValueError:
                    pass

            # loading tolerates a session that has since been deleted...
            assert local_settings.sanitize({"tutor_session": "deadbeef-9999"})["tutor_session"] \
                == "deadbeef-9999"
            # ...but never keeps something that isn't an id at all
            assert local_settings.sanitize({"tutor_session": "../secrets"})["tutor_session"] == ""

            copilot_backend.configure(clean)
            grounding = copilot_backend.grounding_text()
            assert "MEMORY —" in grounding
            assert "retry budget" in grounding and "five per partition" in grounding
            assert "LOCAL TOOLS" in grounding      # sits alongside, doesn't replace

            # a deleted session degrades to no memory rather than an error
            (home / "session-state" / sid / "events.jsonl").unlink()
            copilot_backend._memory_cache["stamp"] = None
            assert "MEMORY —" not in copilot_backend.grounding_text()

            copilot_backend.configure(local_settings.default())
            assert "MEMORY —" not in copilot_backend.grounding_text()
        finally:
            os.environ.pop("COPILOT_HOME", None)
            copilot_backend.configure(local_settings.default())
            copilot_backend._memory_cache["stamp"] = None
    print("ok  tutor session memory (resolve on save, grounding, graceful loss)")


def test_learner_brief_caching():
    """The brief is generated, not read, so a session that's still running
    must not buy a new one every turn."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            sid = "44444444-aaaa-bbbb-cccc-dddddddddddd"
            root = home / "session-state"
            _fake_session(root, sid, [("how does KESTREL route a parcel?",
                                       "it reads the manifest off WREN " + "x" * 2000)],
                          noise=False)
            calls = {"n": 0}

            def fake_call(system, messages, role, **kw):
                calls["n"] += 1
                assert role == "glossary", role          # the cheap model, not the tutor's
                return f"brief-{calls['n']}", 0.25

            real = copilot_backend.call_model
            copilot_backend.call_model = fake_call
            try:
                copilot_backend.configure(
                    local_settings.sanitize({"tutor_session": sid}, strict=True))
                copilot_backend._brief_cache.update(session="", size=0, text="")

                text, cost = copilot_backend.learner_brief()
                assert (text, cost) == ("brief-1", 0.25)

                # a second turn reuses it, and costs nothing
                assert copilot_backend.learner_brief() == ("brief-1", 0.0)
                assert calls["n"] == 1

                # the session grows a little — still the same brief
                events = root / sid / "events.jsonl"
                events.write_text(events.read_text(encoding="utf-8") + json.dumps(
                    {"type": "user.message", "data": {"content": "and then?"}}) + "\n",
                    encoding="utf-8")
                assert copilot_backend.learner_brief() == ("brief-1", 0.0)
                assert calls["n"] == 1

                # it grows materially — now it's worth a fresh one
                events.write_text(events.read_text(encoding="utf-8") + json.dumps(
                    {"type": "assistant.message",
                     "data": {"content": "PLOVER resolves it " + "y" * 9000}}) + "\n",
                    encoding="utf-8")
                text, cost = copilot_backend.learner_brief()
                assert (text, cost) == ("brief-2", 0.25), (text, cost)

                # a failed generation keeps the last good brief instead of
                # breaking the run
                def boom(*a, **k):
                    raise ApiError("copilot fell over", 502)

                copilot_backend.call_model = boom
                copilot_backend._brief_cache["size"] = 1     # force a regen attempt
                assert copilot_backend.learner_brief() == ("brief-2", 0.0)

                # nothing anchored -> nothing generated, ever
                copilot_backend.configure(local_settings.default())
                assert copilot_backend.learner_brief() == ("", 0.0)
            finally:
                copilot_backend.call_model = real
        finally:
            os.environ.pop("COPILOT_HOME", None)
            copilot_backend.configure(local_settings.default())
            copilot_backend._brief_cache.update(session="", size=0, text="")
    print("ok  learner brief caching (reuse, material regrowth, failure, unanchored)")


def test_session_memory_is_tutor_only():
    """The learner and glossary personas must stay uncontaminated roleplay."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        os.environ["COPILOT_HOME"] = str(home)
        try:
            sid = "abc12345-1111-2222-3333-444455556666"
            _fake_session(home / "session-state", sid,
                          [("secret project codename?", "STARLING")])
            copilot_backend.configure(
                local_settings.sanitize({"tutor_session": "abc12345"}, strict=True))
            seen = {}

            def capture(system, messages, role, **kw):
                seen[role] = system
                return ('{"thinking":"t","new_term":null,"action":"a",'
                        '"confidence":10,"done":false}'), 0.0

            routes = model_routes(capture, tutor_grounding=copilot_backend.grounding_text)
            routes["tutor"]({"action": "explain it", "turns": []})
            routes["learner"]({"kind": "root", "topic": "kafka", "turns": []})
            assert "STARLING" in seen["tutor"]
            assert "STARLING" not in seen["learner"], seen["learner"]
        finally:
            os.environ.pop("COPILOT_HOME", None)
            copilot_backend.configure(local_settings.default())
            copilot_backend._memory_cache["stamp"] = None
    print("ok  session memory reaches the tutor only, never the learner")


if __name__ == "__main__":
    test_compose_prompt()
    test_parse_stream()
    test_tool_policy()
    test_overflow_prompt()
    test_local_settings_sanitize()
    test_local_settings_store()
    test_copilot_backend_overrides()
    test_mcp_server_discovery_and_registration()
    test_tree_store()
    test_tree_store_revs()
    test_tutor_store()
    test_global_question_store()
    test_session_reading()
    test_session_names()
    test_session_memory_tracks_a_live_session()
    test_tutor_session_setting()
    test_learner_brief_caching()
    test_session_memory_is_tutor_only()
    print("\nall green")
