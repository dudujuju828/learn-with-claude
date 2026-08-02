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

`call_model(system, messages, role, …)`'s `role` picks the model per backend:
`learner` / `tutor` / `glossary` / `examiner` / `facts` / `reviewer`. Hosted
maps them in `api/index.py`'s `ROLE_MODELS` (examiner and facts →
`claude-opus-5`); local maps them in `copilot_backend.effective_model()`, where
an unknown role means "auto" and no tools. Adding a role means touching both.

`tutor` is the one route that can make **two** model calls: with
`double_check` on the body, the reply goes back out to the `reviewer` role
before it is split into parts (🔍 double-check). Both calls' costs are summed
into the one `cost` the turn is billed. The review can only ever *degrade* —
a failure or an untrustworthy verdict leaves the original answer and puts no
`checked` field on the turn.

**Anything that changes the tutor's brief has to reach the reviewer too.**
`review_system()` quotes `tutor_system()` verbatim so its *contract* defect
kind is enforced against the same text — which means a new argument to
`tutor_system()` that isn't also passed to `review_system()` turns
double-check into a machine for undoing that setting. `mode`, `custom_style`,
`segments` and `max_words` all thread through; `grounding` deliberately does
not (which tools the tutor had is none of the reviewer's business).

The tutor's answer-length ceiling is `personas.TUTOR_WORDS_DEFAULT` (150),
overridden per request by `max_words` on the body (web: *answer length*, per
profile) or `--answer-words` (CLI). Only the ceiling is stored — the rest of
the length clause is derived in `length_rule()`, because a brief saying
"3-6 sentences" under a 400-word cap is one the model resolves by obeying the
tighter half. Never hardcode another length figure into the tutor's prompt.

`illustrate` is the one route that isn't purely `call_model`: stage one is a
normal `tutor` call, stage two goes to Gemini through `gemini_images.py`
(stdlib `urllib`, so the *same* module serves both backends — there is no
per-backend image wiring, and there must not be). It is off unless
`GEMINI_API_KEY` is set, which `/api/me` reports as `images` so the client can
hide the button rather than offer an action that can only fail.

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
  (`profileGlobalQuestions()`) and the custom tutors (`tutorInProfile()`).
  Deliberately global: `allProfiles()` and `adoptTreeProfiles()`, which have
  to see the whole store to work at all.

  A profile has **two halves**, and new code usually needs both:
  *the filing* is a name on the tree doc (`tree.profile`), so it travels in
  `.know.json`; *the registry* is the synced `settings:profiles` doc
  (`api/profiles.js`, `ProfileStore` in `localweb.py`), which is what lets a
  profile exist with zero trees. `allProfiles()` is the **union** of the two —
  never derive existence from the trees alone, that was the old lifecycle
  bug. The registry also owns `active`: which profile you are in is
  server-authoritative, not a device pref, and it carries the per-profile
  tutor style / learner level (`PROFILE_SETTINGS`). Anything that can bring
  trees in (sync, import, drop) must call `adoptTreeProfiles()` so a name
  arriving from the CLI or another device becomes a real record.
- **Nothing enters the glossary automatically.** Terms join only by an
  explicit `➕ add` / flashcard. `✎ define` is a *lookup* that stores nothing.
  `🏷 my words` stores nothing there either — it is an *inline* annotation
  bound to one spot in one sentence (`tree.asides`), not a list entry.
- **The reader's own words must never read as the tutor's.** Asides are
  tinted, underlined, and bracketed with **real characters** — never
  `::before`/`::after`, which don't survive the copy button or the exports.
  Anything else that puts the reader's writing next to the tutor's owes the
  same distinction.
- **Nor as the simulated learner's.** A turn with `user: true` is a question
  the human typed; `🙋 I ask Claude` is the sim speaking, in the same first
  person as the `💭 Thinking to myself` above it. The app (`.action.user-q`),
  both exports, and the CLI's `replay()` each give the human turn its own
  label and colour. 🧑 **free** makes every turn one of these, so a surface
  that renders turns and doesn't check `user` is now wrong on a whole
  conversation rather than on one interjection.
- **A free conversation has no learner to resume.** `node.free` (a `Node`
  field, so it survives `.know.json`) means every turn is the reader's own.
  `canContinue()` returns false for one outright — ▶ continue there would set
  the *simulated* learner loose on a conversation someone deliberately drove
  themselves. Free mode adds no route, prompt, or model role and must not
  grow one: its whole claim is that the answers are the same ones the sim
  would have got.
- **A corrected answer never passes as the original.** 🔍 double-check may
  replace the tutor's words, so a repaired turn always carries *why*
  (`checked.issues`) and *what it said first* (`checked.before`), in the app
  and in both exports. A rewrite the reviewer gave no reason for is refused
  outright rather than shown, and a review that failed leaves no mark at all —
  a `✓ checked` badge on an answer nothing actually read would be worse than
  no badge, since the whole feature is a trust claim.
- **Nothing is illustrated automatically either**, and for the same reason.
  A figure is drawn only from a passage the reader selected, and the
  art-director stage is allowed to answer `{"drawable": false}` — an idea
  with no shape gets no picture. Never "helpfully" widen this: an
  unrequested diagram is a confident picture of the wrong thing.
- **Image bytes never touch a tree.** `api/trees.js` caps a tree at 2 MB and
  the browser holds every tree in one localStorage key, so figures live in
  their own store (`api/images.js` hosted, `knowledge/images/` locally) and
  the tree carries only `{id, node, turn, anchor, caption, alt, …}`. The one
  place bytes are inlined is `export html`, whose page must stay
  self-contained; the client does that on the way out
  (`treeWithFigureBytes`), never in the stored document. A figure id is
  minted per picture and never reused, which is what makes the service
  worker's cache-first rule for `/api/images` correct.
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
python -m pytest -q                     # 54 tests
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
