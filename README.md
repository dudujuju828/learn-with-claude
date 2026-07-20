# learn-with-claude

Grow a **branchable tree of knowledge** by watching a simulated human learner
investigate a topic with Claude — one scoped question at a time.

It runs two separate `claude` CLI sessions (which *are* claude-code) against each
other:

| role | who it is | what it does |
| --- | --- | --- |
| **learner** | a role-played curious human (LLM persona) | emits its private *thinking*, the one unfamiliar *term* it just hit, and the *action* (message) it actually types |
| **tutor** | Claude, held to terse one-idea answers | answers only the exact question, so the learner has to do the work |

The learner takes one small step at a time and, when the tutor uses a word it
can't define, **stops and drills into that word before moving on** — a recursive
descent into unknowns. Then you can pick any tutor answer and have the learner go
back and **re-investigate it more deeply**, growing a branch. The result is a
deliberately *unbalanced* tree — some ideas get explored deeply, most don't —
which is how real understanding actually accretes.

Each tree is a single portable file. Share what you've learned by copying the file.

When a picture genuinely beats words (a workflow, a multi-part structure), the
tutor can additionally **draw an Excalidraw diagram into your Obsidian vault**
via the [excalidraw-skills](https://github.com/dudujuju828/excalidraw_skills)
MCP server, and mentions the note's path in its answer. See
[Diagrams](#diagrams-optional) below.

## Requirements

- **Python 3.8+** (standard library only — no pip installs).
- The **`claude` CLI** installed and logged in (this tool shells out to it). Verify
  with `claude --version`. No `ANTHROPIC_API_KEY` needed; it reuses your auth.

## Install (the `learn` command)

To launch from any terminal by just typing `learn`:

**Windows (one-liner):**

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

This drops a `learn` launcher into `~/.local/bin` (cmd, PowerShell, and Git Bash
all pick it up) pointing at this repo. Open a new terminal and run `learn`.

**Or via pip** (any OS — gives a `learn` entry point + `python -m learn_with_claude`):

```bash
pip install -e .
```

> On Microsoft Store Python the pip Scripts dir often isn't on PATH; if `learn`
> isn't found after `pip install`, use `install.ps1` or `python -m learn_with_claude`.

Trees are stored in `~/.learn-with-claude/knowledge` by default (so the global
command keeps everything in one place). Override with `--dir` or the `LEARN_DIR`
environment variable.

## Web app (self-hosted on Vercel)

The same learner↔tutor loop as a password-protected web app — open a link on
any device, log in, and grow trees. Prompts, models (`claude-sonnet-5` @
`xhigh`), loop semantics, and the `.know.json` format are identical to the
CLI; the only difference is that the server calls the Anthropic **API**
directly (a local `claude` login can't run on a server), so it needs an
`ANTHROPIC_API_KEY` and bills per token at the same ~$0.05–0.07/turn.

- `api/index.py` — stateless backend: login (HMAC cookie from `APP_PASSWORD`),
  one endpoint per model step; imports `personas.py` / `knowledge.py` /
  `render.py` / `simulator.py` unchanged.
- `api/trees.js` — tree history in Vercel Blob (`trees/<id>.json`), so every
  logged-in device sees the same past investigations. The browser keeps a
  localStorage working copy and syncs (debounced push, boot merge,
  last-write-wins per tree).
- `public/index.html` — the shell as a dyslexia-friendly page: font switcher
  (OpenDyslexic / Lexend / Atkinson / Comic Sans), six colour themes
  (including a black **high-contrast** theme with every text pairing at
  WCAG AAA, for low-vision readers), text /
  line / letter / word spacing, keyboard-only **reading ruler** and
  **focus line** (typoscope) stepping visual lines, read aloud (per block, or
  🔊 listen through a whole conversation — with your pick of the browser's
  voices and a 0.5–2× speed control, a ▶ sample button to audition them,
  and the word being spoken highlighted in the text as you listen,
  karaoke-style),
  **search across every tree** (turns, glossary, and your own notes and
  highlights — a note hit opens the notes editor, a highlight hit jumps to
  the marked passage),
  branch buttons under every answer (plus a **loose threads** list of the
  words the learner flagged but never chased — tap one to branch straight
  into it, or ✕ to dismiss the ones you don't care about, ↩ to bring them
  back), live cost, and `.know.json`
  import/export compatible with the CLI (plus the CLI's standalone HTML
  reading page via *export html*; dropping `.know.json` files anywhere on
  the page imports them, and on phones and tablets every export opens the
  OS share sheet — AirDrop, Save to Files, Drive — instead of a download). A **tutor style** picker switches the
  answers between balanced / highly technical / precise / simple / concise
  (the original terse style), applied from the next turn — or write your own
  **custom tutor** (name + how it should answer, with a try-before-saving
  preview), which syncs across devices like the trees and keeps the base
  rules in force. A **learner** picker sets how much the simulated learner
  already knows (curious novice → student → practitioner → expert from a
  neighbouring field), so its questions scale with the tutor; **auto** (the
  default) derives the level from the tutor style, and each investigation
  keeps the learner it started with. For a broad topic, **🗺 survey** maps
  before diving: one model call breaks it into the foundations it's built on
  (each with a one-line why, two levels deep, any piece expandable further);
  *investigate* runs a normal conversation on a piece — the first roots the
  tree, later ones carry the usual follow-up recap — and the map stays with
  the tree, tracking coverage, so you pick off the rest whenever — and
  **know it** marks a foundation you already understand as covered without
  spending a conversation on it. Tutor
  answers arrive **marked up into
  parts**: the direct answer first, then each distinct aspect (the why, an
  example, a caveat…) as its own labelled fold-out card, so a long answer
  reads one idea at a time. Every term the learner hits lands in a
  **glossary with real definitions** — written the moment the term appears
  (a cheap haiku call in parallel with the tutor), stored inside the tree so
  they sync, export, and travel in `.know.json`; defined terms get a dotted
  underline wherever they appear in answers (tap for the definition in a
  popover), the sidebar glossary unfolds each term with a jump back to where
  it came up (and an *✎ edit* to fix any auto-written definition by hand —
  the correction rides the sync and wins the merge), old trees backfill with
  one *define missing* click, and your
  own unknowns count too: **select a word or two in any answer** and a
  floating chip offers *✎ define* — the term joins the glossary with the
  same machinery (underlines, flashcards, export; *✕ forget* removes it
  again) — or *⛏ dig*, for when a definition isn't enough: the tutor is
  asked what that thing actually **is** in this context, and the answer
  lands in the conversation as your own turn (🧑), where you can read it,
  define terms inside it, or branch from it. Select a longer stretch and the
  same chip offers **★ highlight** — a highlighter over the tutor's words
  that stays put across reloads and devices (tap a mark to lift it), travels
  in `.know.json`, and shows up in both exports — the Markdown quotes each
  marked passage under its turn, the HTML reading page bands it in
  highlighter colour. A **★ highlights** hub in the words tab collects
  every marked passage across the profile's trees; tap one to jump back to
  it in context. **anki
  cards** downloads the defined terms as a file Anki imports directly — or
  skip the export: **🔁 review** turns every defined term into
  an in-app flashcard (recall → flip → grade yourself again / good / easy,
  fix a card's definition inline the moment you spot it's wrong, or tap
  🔊 — the **s** key — to hear the term or its answer pronounced in your
  chosen voice; a **⌨ type** toggle turns the deck around into typed
  recall — the definition asks, you type the term, and the check is
  forgiving: case, punctuation, and one typo or swapped pair of letters
  read as *close*, not wrong, and the final grade stays yours),
  scheduled out on a spaced-repetition ladder (1d → 3d → ×2.5) so each card
  comes back just before you'd forget it; the schedule lives on the glossary
  entry, so it syncs across devices and travels in `.know.json`. The due
  count follows you out of the app: the browser-tab title reads *(n) topic*
  while cards are waiting, and an installed PWA carries the count on its
  app icon. A **📊
  progress** panel turns that review-and-quiz data into an at-a-glance view —
  recall strength (card maturity), a 14-day review forecast, your current
  streak, and quiz history — scoped to the active profile. Trees file
  under **profiles** — named interest areas like *computer-science* — and the
  active profile scopes the tree list and the review deck, so each interest
  keeps its own flashcards; the profile name lives on the tree document and
  syncs, merges, and exports with it (and the ✎ chip renames a profile
  across every tree filed under it). **🎓
  quiz me** writes a handful of multiple-choice questions from what the tree
  actually covered (one model call, kept with the tree — retakes just
  reshuffle), explains every answer, and records your scores. Each tree also
  gets **📝 my notes** — a free-text space for your own synthesis of what you
  learned, which autosaves, syncs with the tree, and heads every export. You
  can also **ask the tutor yourself** under any conversation — your question
  is answered with the node's context and stored as your own turn
  (`user: true`), which the simulated learner never sees. Conversations
  interrupted mid-run offer **▶ continue**; URLs deep-link to the exact tree
  and node, and reopening the app puts you back at the exact spot you last
  scrolled to in a conversation — the bookmark survives reloads and mobile
  tab evictions. On a phone the whole thing drives from a **bottom tab bar**
  (read / grow / tree / words / find) whose sections open as thumb-reachable
  bottom sheets, with the ask box sticky above it and everything sized for
  fingers.

Deploy your own: `vercel deploy --prod`, then `vercel env add APP_PASSWORD
production`, `vercel env add ANTHROPIC_API_KEY production`, and `vercel blob
store add <name>` (linked to the project) for history. Not in the web app:
tutor diagrams (they need a local Obsidian vault), `many`, `seeplusplus`.

## Local web app (no keys — GitHub Copilot)

The same web app served from your own machine, with model calls going through
the **GitHub Copilot CLI** instead of the Anthropic API. No API key, no
password, no cloud storage — nothing leaves the machine except Copilot's own
traffic, and turns bill against your Copilot subscription's premium requests
(the default `auto` model routing often lands on free-multiplier models, so
many turns cost 0).

```bash
npm install -g @github/copilot   # the Copilot CLI
copilot                          # once, to log in with GitHub, then /exit
learn --web                      # serves http://localhost:8577 and opens it
```

How it differs from the Vercel deployment:

- **No login** — the server binds 127.0.0.1 only and `/api/me` always answers.
- **Trees are files** — they persist straight into the CLI's knowledge dir
  (`$LEARN_DIR` or `~/.learn-with-claude/knowledge`), so the `learn` shell and
  the web app grow one collection and your existing trees appear immediately.
  Custom tutors live beside them in `tutors.json`.
- **Costs are premium requests, not dollars** — the header counts `req`
  as reported by the CLI per call; trees grown against the API keep their `$`.
- **The tutor can ground itself locally.** Its Copilot session gets
  **read-only** tools (`view`, `grep`, `glob` — never shell, write, or web)
  with file access from your home directory down, so when a question touches
  material you have on disk, it can go look. The learner, glossary, and quiz
  roles run with no tools at all.

Options: `--port` (default 8577), `--dir` for the knowledge folder,
`--no-open` to skip the browser. Env knobs: `LEARN_COPILOT_MODEL` (or
per-role `LEARN_COPILOT_LEARNER_MODEL` / `_TUTOR_MODEL` / `_GLOSSARY_MODEL`)
to pin a model instead of `auto`, `LEARN_EFFORT` for reasoning effort on
models that support it, `LEARN_TIMEOUT` per call, `LEARN_COPILOT_EXE` if the
CLI lives somewhere unusual. `python -m learn_with_claude.localweb` works
without installing the `learn` command.

## Quick start

```bash
learn                       # open the interactive knowledge shell
learn "what a hash table is" # start a tree, then drop into the shell
learn "hash tables" --once   # start a tree and exit (non-interactive)
learn "B-trees" --level expert  # a learner who already knows adjacent fields
                                # (novice / student / practitioner / expert)

# without installing, the equivalent is:  python learn.py [topic]
```

## The shell

```
learn (what a hash table is) › tree
● [1] what a hash table is  (3 turns · conf 25%)
└─ ● [2] collisions specifically  (↳T2 · 3 turns · conf 35%)

learn (what a hash table is) › branch 1 2 collisions
... learner re-investigates node 1's tutor answer at turn 2, going deeper ...
```

| command | what it does |
| --- | --- |
| `new <topic>` | start a new tree and run the root investigation |
| `full <topic>` | like `new`, but after each investigation the tutor reviews what was covered and picks the **next best related concept** (a why/how/when-style angle, not another "what is") for the learner to explore — you end up with 4 linked investigations in one tree, so the exported map is a small tour of the topic |
| `many "<q1>", "<q2>", …` | run one `new` investigation per quoted question, all **in parallel** (4 at a time); each conversation replays in full as it finishes and is saved as its own tree, and the first question's tree is left open |
| `branch <node> <turn> [focus]` | re-investigate that node's tutor answer at `<turn>`, going deeper. `[focus]` steers what to dig into; omit it and the learner picks. |
| `tree` | show the current tree |
| `show <node>` | replay a node's full conversation |
| `open <file\|index>` | load a tree from the knowledge dir |
| `list` | list trees in the knowledge dir |
| `import <path>` | copy an external `.know.json` in and open it |
| `export [file]` | write the whole tree to a readable markdown file |
| `seeplusplus <file> [out]` | (alias `spp`) export a C++ source file to the same dyslexia-friendly HTML page — one row per line with line numbers and light theme-aware syntax tinting, and the full reading-aids toolbar: fonts, themes, spacing, arrow-key line stepper, focus line, invert on step, read aloud (click a line) |
| `save [file]` | save (auto-saves after `new`/`branch`) |
| `cost` | total spend on the current tree |
| `help` · `quit` | help / leave |

`<node>` and `<turn>` are the bracketed ids shown by `tree` (e.g. `branch 1 2`).

## Diagrams (optional)

Give the tutor a drawing hand:

```bash
npm install -g excalidraw-skills          # the MCP server that renders diagrams
learn "how DNS resolution works" --vault "C:/path/to/your/vault"
```

Instead of `--vault` you can set `EXCALIDRAW_VAULT_PATH` (or `OBSIDIAN_VAULT_PATH`)
once. Diagrams land in `Excalidraw/Lessons/` inside the vault (override with
`EXCALIDRAW_FOLDER`); open them in Obsidian with the Excalidraw plugin. The tutor
is prompted to draw sparingly — only when a structure or process is easier to see
than to read — and still answers in its usual terse style.

If no vault or server is found, or with `--no-diagrams`, the tutor is pure text,
as before. The tutor never gets any other tool; both personas run with the
built-in tools disabled and `--strict-mcp-config`, so your globally registered
MCP servers are never exposed to them.

## How branching works

When you `branch <node> <turn>`, the tool seeds a *fresh* learner↔tutor conversation
with the context the learner already has, so it builds on prior knowledge instead of
restarting:

- the learner is told its **breadcrumb** (`hash table › collisions`) and a **digest**
  of the Q&A it already covered, then pointed at the specific tutor answer to dig into;
- the tutor's system prompt gets that same digest so it **doesn't re-explain the basics**.

So a branch off a turn-2 answer starts the learner around the confidence it had
reached there and descends a new chain of unknowns from that point.

## Accessibility (dyslexia-friendly)

**Sentence spacing** — tutor answers are reflowed so every sentence sits in its own
paragraph with an empty line between them, which makes each line much easier to track.
This is enforced twice: the tutor is prompted to write that way, and the text is
normalised in code anyway, so terminal output, the HTML export, and the markdown
export all get it — including trees saved before this feature existed.

**In the terminal** — a program can't change the terminal's *font* (that's a setting
in your terminal emulator), but the layout is tuned for readability: short ~64-char
lines, sentence case (never ALL CAPS), high-contrast body text in your terminal's own
colour, each block wrapped in a labelled colour gutter so it reads as one chunk, no
italics, and generous spacing. Tune it with `--width` and `--line-spacing 2`.

**In the export** — `export html` writes a self-contained page that actually uses a
dyslexia-friendly *typeface*, with an in-page toolbar to switch between **OpenDyslexic /
Lexend / Atkinson Hyperlegible / Comic Sans / system**. The page uses a cream background
with dark-but-not-black text, 1.75 line-height, extra letter/word spacing, a ~64-character
measure, left alignment, and a clickable map of the tree. Fonts load from web CDNs with
offline fallbacks to Comic Sans / Verdana (both dyslexia-friendly), so it degrades
gracefully without a connection.

The toolbar also has:

- **text size** and **line spacing** (up to ~4× — very airy), **letter spacing** and
  **word spacing** controls;
- **colour themes** — cream, soft blue, soft green, grey, and dark (tinted backgrounds
  help many dyslexic readers);
- **↵ sentence per line** — every sentence starts on its own line, across all blocks;
- **🖍 reading ruler** — a tinted band steered **only by the arrow keys** (←/→ or
  ↑/↓; the mouse never moves it): it snaps to the text and steps one line at a
  time, auto-scrolling so the current line stays centred, teleprompter-style;
- **🕶 focus line** — hides *everything* except the current line (like a typoscope
  card over the page), stepped with the same arrow keys. It stands alone — no
  yellow band, the revealed line is the implicit ruler — or turn the reading ruler
  on too if you want the line tinted amber;
- **🌓 invert on step** — optionally flip the page to its inverse colours on every
  ruler step and back on the next, a strong pacing cue that each press landed;
- **🔊 read aloud** — click any block of text to hear it via the browser's built-in
  speech synthesis (Esc stops it);
- **🤖 ask AI** — with the ruler or focus line on a line, press **A** (or the button):
  a panel opens where you can ask DeepSeek (`deepseek-v4-pro`) about that exact line.
  Tap **Right Shift** to toggle between ruler control and the question box (arrows step
  lines on one side, edit text on the other; it recaptures whatever line you're on),
  and type `cls` in the box to clear the answer area —
  on code pages it sends the line plus ~20 lines of surrounding context. Answers come
  back short and sentence-per-line. The key is read at export time from
  `DEEPSEEK_API_KEY` or `~/.deepseek_key` and baked into the exported HTML, so **treat
  exported pages as private** (the `knowledge/` dir is gitignored for this reason);
- a **reset** button, and all settings persist across reloads (localStorage).

```
learn (...) › export html        # → knowledge/<topic>.html
learn (...) › export md notes.md # → markdown to a chosen path
```

## The data structure

A **knowledge tree** is one file: `knowledge/<topic>.know.json`.

- **Node** = one investigation (a learner↔tutor conversation). Fields: `id`, `label`,
  `parent_id`, `branch_from_turn`, `focus`, `turns[]`, `children[]`, `cost`,
  `final_confidence`, models, timestamp.
- **Tree** = a flat `id → node` map plus `root_id`, so the (unbalanced) shape is just
  parent/child links — trivial to serialise, navigate, and merge by copying files.
- A **turn** is `{turn, thinking, new_term, action, confidence, done, tutor}`.

"Importing knowledge" is literally copying a `.know.json` into your `knowledge/` dir
(or `import <path>` in the shell).

## Project layout

```
learn.py                      # entry point (python learn.py ...)
install.ps1                   # installs the global `learn` command into ~/.local/bin
pyproject.toml                # packaging + `learn` console-script entry point
learn_with_claude/
  __main__.py                 # enables `python -m learn_with_claude`
  backend.py                  # ClaudeSession — wraps `claude -p`, resumes by session id
  diagrams.py                 # optional excalidraw-skills MCP wiring for the tutor
  personas.py                 # learner/tutor prompts + root & branch message templates
  simulator.py                # run_conversation() — the reusable learner<->tutor loop
  knowledge.py                # Node + KnowledgeTree: persistence, navigation, render, md export
  export_html.py              # dyslexia-friendly HTML export (font switcher + accessible CSS)
  repl.py                     # the interactive knowledge shell
  render.py                   # dyslexia-friendly terminal formatting / colour / Windows UTF-8
  cli.py                      # argument parsing & dispatch
  webapi.py                   # the /api route handlers, shared by both web backends
  copilot_backend.py          # GitHub Copilot CLI as a model transport (local web app)
  localweb.py                 # `learn --web` — the web app on localhost, trees on disk
knowledge/                    # your saved trees (*.know.json) + exported markdown
```

## Options

| flag | default | meaning |
| --- | --- | --- |
| `topic` | – | optional topic to start a tree on |
| `-n, --max-turns` | `20` | per-investigation safety cap (learner usually stops sooner) |
| `-m, --model` | `claude-sonnet-5` | model for both personas (`opus`, `claude-opus-4-8`, …) |
| `--learner-model` / `--tutor-model` | = `--model` | per-persona override |
| `--effort` | `xhigh` | reasoning effort for both personas (`low`…`max`) |
| `--vault` | env vars | Obsidian vault for tutor diagrams (see [Diagrams](#diagrams-optional)) |
| `--no-diagrams` | off | force the pure-text tutor |
| `-d, --dir` | `knowledge` | knowledge directory |
| `--width` | `66` | terminal wrap width (dyslexia-friendly short measure) |
| `--line-spacing` | `1` | `2` adds a blank line between lines for extra airiness |
| `--once` | off | with a topic: create the tree and exit |
| `--timeout` | `300` | per-call timeout (seconds) |
| `--no-color` | off | disable ANSI colour |

## Notes & limitations

- **It costs money.** Every turn is two real model calls — roughly $0.05–0.07/turn on
  `sonnet`. A root investigation usually self-stops in a handful of turns; each branch is
  another small conversation. Keep `--max-turns` modest and use `sonnet` to stay cheap.
- The tutor is a *conceptual* tutor (no filesystem, no tools beyond the optional
  diagram pen), deliberately terse to force granular learning.
- The learner is a simulation of a plausible human, not a specific person; runs are
  non-deterministic.
