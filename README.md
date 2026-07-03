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

## Quick start

```bash
learn                       # open the interactive knowledge shell
learn "what a hash table is" # start a tree, then drop into the shell
learn "hash tables" --once   # start a tree and exit (non-interactive)

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
| `branch <node> <turn> [focus]` | re-investigate that node's tutor answer at `<turn>`, going deeper. `[focus]` steers what to dig into; omit it and the learner picks. |
| `tree` | show the current tree |
| `show <node>` | replay a node's full conversation |
| `open <file\|index>` | load a tree from the knowledge dir |
| `list` | list trees in the knowledge dir |
| `import <path>` | copy an external `.know.json` in and open it |
| `export [file]` | write the whole tree to a readable markdown file |
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
- **🖍 reading ruler** — a tinted band that follows your mouse to keep your place; the
  **arrow keys** (←/→ or ↑/↓) snap it to the text and step it one line at a time,
  scrolling as needed (move the mouse to take back free control);
- **🕶 focus line** — hides *everything* except the current line (like a typoscope
  card over the page); works with both mouse-following and arrow-key stepping. It
  stands alone — no yellow band, the revealed line is the implicit ruler — or turn
  the reading ruler on too if you want the line tinted amber;
- **🌓 invert on step** — optionally flip the page to its inverse colours on every
  ruler step and back on the next, a strong pacing cue that each press landed;
- **🔊 read aloud** — click any block of text to hear it via the browser's built-in
  speech synthesis (Esc stops it);
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
