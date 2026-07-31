# learn-with-claude — working notes

What the README doesn't say: how to work on this repo without stepping on a
rake. Read `README.md` for what the app *does*; this is the operational stuff.

## Deploying — always manual

**Vercel does not build on `git push`.** There is no Git integration (and the
repo is private now, so wiring one up would also need repo access granted to
the Vercel GitHub App). After pushing anything that touches `public/`, `api/`,
or `learn_with_claude/`, the hosted app stays on the old build until you run:

```bash
vercel deploy --prod --yes
```

Then confirm it actually shipped — a stale hosted build has masked "the button
isn't there" more than once:

```bash
curl -s https://learn-with-claude.vercel.app/ | grep -c <someNewFunctionName>
```

## The one seam worth knowing

`learn_with_claude/webapi.py::model_routes()` is the route table **both** web
backends serve — hosted (`api/index.py`, Anthropic API) and local
(`localweb.py`, Copilot CLI). Every route is one stateless model call; the
learner↔tutor *loop* lives in the browser (and in `simulator.py` for the CLI).

Adding a route means three things, and the third is easy to forget:

1. a handler in `webapi.py`
2. an entry in the `model_routes()` dict
3. **the route name added to `vercel.json`'s rewrite list** — miss this and it
   works locally and 404s in production

## Three deployment targets, one frontend

- **CLI** (`learn`) — `repl.py`/`cli.py`, model calls via `claude -p`.
- **Local web** (`learn --web`) — `localweb.py` + `copilot_backend.py`.
  No API key, no password, trees are files.
- **Hosted** — `api/index.py` + the `api/*.js` Postgres sync routes.

`public/index.html` is a single ~9k-line file shared by both web targets, and
it holds all client state. The Python package is **stdlib-only**; `anthropic`
is imported by `api/index.py` alone. Don't add dependencies casually.

To run locally: `python learn.py --web` (no install needed).

## Invariants for anything stored on a tree

A new field on a tree or a turn has to survive four things. Check all of them:

1. **`mergeTrees()`** in `public/index.html` — the sync unions by id and
   generally lets the *server* copy win. A field that a device edits locally
   needs an explicit merge rule, usually "newer stamp wins" (see `glossary`
   `edited`, the questions' `seq`/`ordered`, the `gone` tombstones).
2. **`.know.json`** — top-level keys survive the CLI via
   `KnowledgeTree.extras`; unknown *turn* keys pass through as raw dicts.
   Unknown **node** keys are dropped (`_NODE_FIELDS` filters them) — add the
   field to the `Node` dataclass if it belongs there.
3. **Both exports** — `knowledge.to_markdown()` and `export_html.py`.
4. **Profiles** (below).

## Rules the app has committed to

Breaking one of these is a regression even if nothing errors.

- **Profiles scope everything.** Any new view that walks `Object.values(store)`
  must use `profileTrees()` instead. Same for the global question bank
  (`profileGlobalQuestions()`). Deliberately global: the `save all` backup,
  `allProfiles()`, and custom tutors.
- **Nothing enters the glossary automatically.** Terms join only by an
  explicit `➕ add` / flashcard. `✎ define` is a *lookup* that stores nothing.
- **The simulated learner stays ignorant.** It never sees the human's own
  turns, and in local mode it gets a generated *orientation brief* (names and
  what kind of thing each is), never the anchored session's transcript. Its
  naivety is the engine of the whole tool.
- **Notes are markdown**, rendered live in a contenteditable. Two renderers
  implement the same subset and must stay in step: `noteInlineHtml`/
  `noteLineHtml` (JS, the editor) and `note_md()` (Python, the HTML export).
  Both escape first, then build only their own tags.
- **The tutor gets no tools** except in local mode, where `--strict-mcp-config`
  still keeps the operator's global MCP servers out of the personas.

## Testing

```bash
python -m pytest -q                     # 34 tests
python tests/test_web_helpers.py        # also runs standalone
python tests/test_copilot_local.py
```

The frontend has no test framework. The established pattern is a **stub
harness driven by headless Edge** — build a copy of `public/index.html` with a
`<script>` injected before the main one that seeds `localStorage` and replaces
`window.fetch` with canned JSON, append a probe script before `</body>` that
writes `PASS`/`FAIL` lines into a `<pre>`, then read it back out of
`--dump-dom`. Examples live in the session scratchpad as `make_*.py`; the
pattern is worth rebuilding rather than skipping, it has caught real bugs
(undo popping the wrong entry, a reorder deleting other profiles' questions).

Gotchas that cost time:

- Top-level `let`/`function` in the page are visible as bare identifiers from
  a later `<script>`, so a probe can call `cur()`, `noteSource()`, `store`
  directly. No `window.` exports needed.
- `/api/me` **replaces** `CONFIG` wholesale — a stub must include
  `max_turns` or the learner↔tutor loop never enters its for-loop.
- `searchHits(q, …)` expects an **already-lowercased** query.
- Synthetic text selections often miss the debounced `selectionchange`
  listener on the first try — fire them 2-6 times, and rebuild the Range each
  time (a background sync re-render orphans the nodes you captured).
- Headless `--screenshot` one-shots render with **print** media, and
  `@media print` hides every modal. To screenshot a dialog, drive the browser
  over CDP and use `Page.captureScreenshot`.
- Cheap post-edit gate: extract the `<script>` bodies and `node --check` them,
  and assert the `<style>` block's `{`/`}` counts match.

## Conventions

- `NOTES.md` is a feature log, newest first: what was chosen, why, and what
  was rejected. Add an entry for anything substantial. Past entries are a
  dated record — don't rewrite them to match the present.
- Commit messages are human-style prose, no AI attribution, and explain the
  *why* (especially when a decision looks odd — e.g. why session memory is
  read rather than `--resume`d).
- Frontend comments explain the reasoning, not the mechanics. Match that.
