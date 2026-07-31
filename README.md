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
  `render.py` / `simulator.py` unchanged. Roles map to models here: the
  learner and tutor run on `claude-sonnet-5`, glossary definitions on a cheap
  fast model, and the **examiner** (📄 exam's paper-setter and marker) on
  `claude-opus-5` — setting a fair paper and marking essays to a scheme are
  the two judgement calls whose failures are least visible to the person they
  land on, since a soft mark reads exactly like a good one. Set
  `LEARN_EXAMINER_MODEL` to bring it back down to the tutor's model.
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
  karaoke-style — in a long block the page follows the spoken word, gliding
  it back into view, until your own scrolling takes over),
  **search across every tree** (turns, glossary, and your own notes and
  highlights — a note hit opens the notes editor, a highlight hit jumps to
  the marked passage; spelling is forgiven the way the typed-recall
  checker forgives it — if nothing matches exactly, a word one typo or
  one swapped letter-pair away still counts, in any word order, and the
  results say "close matches" — the same forgiveness the glossary filter
  and ⌘K apply),
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
  spending a conversation on it. For a topic you half-know, **🧭 gaps**
  turns Ausubel's rule into a button — a short interview before the
  digging: the tutor asks a few questions one at a time, following what
  your answers reveal (probing a belief that sounds off, sampling what you
  didn't mention; "no idea" is a perfectly good answer), and stops as soon
  as it can place you — or when you say *that's enough — map me*. Then it
  maps what's solid, what's shaky, and what's missing, and the
  investigation starts at the biggest gap: the learner opens at your
  evident level, the tutor never re-explains what you have down and
  straightens your shaky beliefs as they come up, and the map and
  transcript stay on the tree (reopen them from the conversation header)
  and sync and travel like everything else. When a real interview is more
  than you need, **✓ skip what you already know** — the fold right above
  **gaps** — is the fast path: list what you've already got, one per
  line, no interview, no extra model call. It applies to `new`/`full` the
  same way, feeding the identical "don't re-ask/re-explain this" contract
  straight from what you typed instead of from a diagnosed assessment.
  **📚 ground it in your own
  material** — a fold under the topic box — takes `new` or `full` in a
  different direction: paste a passage (a textbook section, an article,
  your notes) and the whole tree grounds itself in it — the learner's
  questions anchor to what it actually says, the tutor answers from it
  and says plainly when it's wrong or oversimplified. The passage travels
  and syncs with the tree, a **📚 source** button in the conversation
  header reopens or corrects it, and it's quoted at the top of both
  exports. On any tree, **→ next** in the conversation
  header hands one step to the tutor: it reviews everything covered so far
  and picks the single concept that best builds on it — a why/how/when
  angle rather than another "what is" — then runs that follow-up
  investigation, keeping its one-line *why* on the new conversation (the
  same step `full` chains four of). Next to it, **🔬 look deeper** (once a
  conversation is finished) is the opposite move: the SAME concept again,
  not a new one, as a full fresh investigation seeded with everything
  already covered so it never repeats itself — the simulated learner is
  pushed to expert level and the tutor is told to set its usual brevity
  aside, so the result is internals, edge cases, and tradeoffs, not another
  pass over the basics. Tutor
  answers arrive **marked up into
  parts**: the direct answer first, then each distinct aspect (the why, an
  example, a caveat…) as its own labelled fold-out card, so a long answer
  reads one idea at a time. The **glossary** is strictly yours:
  **nothing lands in it automatically** — not the words the learner
  flagged, not the ones the tutor leaned on. A word joins only when you
  put it there: **select a word or two in any answer** and the floating
  chip's ***➕ add*** files it, or tap the 🔍 word the learner flagged to
  add that one. Adding is **free** — no model call, no definition — so
  you can curate as you read and buy the definitions later. The sidebar
  glossary unfolds each term with a jump back to where it came up, an
  *✎ define it* per term (or *define N missing* for the whole list at
  once) on the cheap model, an *✎ edit*
  to fix any definition by hand (the correction rides the sync and wins
  the merge), a *✕ forget* that takes a word back out for good (a
  tombstone travels with the tree, so another device's copy can't put it
  back), and defined terms get a dotted underline wherever they
  appear in answers (tap for the definition in a popover).
  The chip's *✎ define* is a **lookup, not an add** — it tells you what a
  word means and leaves the glossary alone; if the answer was worth
  keeping, the popover's *➕ add to glossary* keeps it, definition and all,
  without paying for it twice. Next to them sits ***+ flashcard***,
  which folds out four angles — *definition*, *purpose*, *example*, *how
  it works* — the model drafts whichever one you pick, and the draft
  lands in an editable box with *add* / *cancel* so you can tweak the
  wording before anything is actually saved; a term can carry more than
  one reasoned card, each tagged with a small badge in the words tab, the
  review deck, and the anki/study-sheet exports. Or **💬 ask**, when you have a
  question of your own about that exact sentence: a small bar opens with the
  passage quoted above it, you type the question, and it goes straight to the
  tutor with the passage attached — so the answer is about *that claim*, not
  the topic in general. It lands in the conversation as your turn (🧑) with
  the passage shown above it, and travels that way into both exports.
  Or *⛏ dig*, for when a
  definition isn't enough: the tutor is
  asked what that thing actually **is** in this context, and the answer
  lands in the conversation as your own turn (🧑), where you can read it,
  define terms inside it, or branch from it. **▶ investigate** is dig's big
  sibling: it takes exactly what you selected — a term or a whole sentence —
  and starts a fresh investigation on it in **its own tree**, carrying
  nothing over from what you were reading (no digest, no breadcrumb, no
  grounding passage), precisely as if you'd typed that text into the topic
  box and pressed *new*. It inherits only what a new tree always inherits:
  the active profile, the tutor style, and the learner level.
  The same chip also offers
  **★ highlight** — a highlighter over the tutor's words
  that stays put across reloads and devices (tap a mark to lift it), travels
  in `.know.json`, and shows up in both exports — the Markdown quotes each
  marked passage under its turn, the HTML reading page bands it in
  highlighter colour. A **★ highlights** hub in the words tab collects
  every marked passage across the profile's trees; tap one to jump back to
  it in context. **📅 today** collects everything *actionable* across the
  profile in one place — cards due, conversations due another
  explanation, loose threads from every tree (not just the open one),
  survey maps with uncovered ground — each a tap from doing it, so the
  session starts with a list instead of a wander. **📜 study sheet**
  compiles the whole profile into one revision document: each tree's
  notes, your best explanation of each conversation (verdict included),
  the passages you highlighted, and every defined term merged into a
  single alphabetical glossary — the sheet you'd revise from before an
  exam, saved through the same share-sheet path as every export. **anki
  cards** downloads the defined terms as a file Anki imports directly — or
  skip the export: **🔁 review** turns every defined term into
  an in-app flashcard (recall → flip → grade yourself again / good / easy,
  fix a card's definition inline the moment you spot it's wrong, or tap
  🔊 — the **s** key — to hear the term or its answer pronounced in your
  chosen voice; a **⌨ type** toggle turns the deck around into typed
  recall — the definition asks, you type the term, and the check is
  forgiving: case, punctuation, and one typo or swapped pair of letters
  read as *close*, not wrong, and the final grade stays yours; **↩**
  — the **u** key — takes back a fat-fingered grade, restoring the
  card's schedule exactly; and **🎧 drill** — the **d** key — runs the
  deck hands-free, out loud: the term is spoken, a recall pause follows
  — you set its length, and a thin bar fills as it runs — then the
  answer, and after a beat the card is marked *good* and the next one
  starts, the screen held awake throughout. Press 1–3 at any moment to
  grade a card yourself instead — a mis-heard card deserves *again* —
  and the session summary owns up to every grade the drill gave
  itself),
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
  active profile scopes **everything**, not just the tree list: the glossary
  (both its this-tree and all-trees views), the review deck, search, the ⌘K
  palette, 📅 today, the highlights hub, the study sheet, 📊 progress, and the
  global question bank. Switch profile and the whole app is about that
  interest; each keeps its own flashcards, its own banked questions, its own
  everything. With no profile selected you see the lot. The name lives on the
  tree document (and on each banked question), so it syncs, merges, and
  exports with them — and the ✎ chip renames a profile across every tree
  *and* question filed under it. **🎓
  quiz me** writes a handful of multiple-choice questions from what the tree
  actually covered (one model call, kept with the tree — retakes just
  reshuffle), explains every answer, and records your scores; the 🔊 beside
  the question — or the **s** key — reads it and each choice aloud, then the
  explanation once you've answered. **📄 exam** is the quiz's harder
  sibling — a written paper on the conversation you have open, where nothing
  can be answered by recognising it. Pick a length (3–8 questions, 5 by
  default) and the examiner sets essay questions *from* that conversation
  without ever quoting it: explain a mechanism, apply the idea to a case that
  never came up, predict what a change would do, take apart a claim that
  sounds right. One box per question, one submit at the end, **10 marks**
  each. Every question is set together with the mark scheme it will be marked
  against, and the marker is held to that scheme — so two sittings are judged
  to one standard rather than to whatever the model felt like that day. What
  comes back per question is two paragraphs — what your answer earned, and
  what a full-mark answer would have said — plus the scheme points you hit and
  missed, a mark, and one comment on the script as a whole. Marks go to the
  ideas and the reasoning first, with credit for using the technical
  vocabulary correctly: never for name-dropping it, and never lost for
  explaining the right thing in plain words. A blank answer scores 0 and comes
  back with a model answer, so it still teaches you something. Answers save as
  you type — a paper survives closing the tab, and an unfinished one waits in
  📅 today — any question you can't answer goes to the global bank with
  **❓ bank it** without breaking off the sitting, and the marked script syncs,
  travels in `.know.json`, and heads into both exports.
  **🗣 explain it back** is
  the Feynman loop: explain a conversation in your own words, from memory,
  as if teaching a friend, and the tutor reads it against what was actually
  covered and answers with what's solid, the one gap that matters, one
  question to push deeper — and an honest verdict (✓ clean / ≈ close /
  △ gappy) — feedback on the ideas, never the spelling. The tutor keeps
  probing: the box turns into answering that one question (shown right
  above it, and **Enter** sends the reply — no scrolling, no reaching for
  the mouse) instead of re-explaining everything, and each reply is judged
  against the whole thread so far, not from zero. A **clean** round is
  praise, not a reset — the tutor still leaves a real next question on the
  table and never re-flags something already covered as missing; keep
  going for as long as there's something worth chewing on, or just close
  the box. That whole thread stays visible above the box as you go — what
  you said, what it asked next — so what the tutor is weighing is never
  hidden. Every reply is kept (synced, travelling in `.know.json`), the
  verdict trail shows the thread narrowing, and **⤳ chase it** sends
  the tutor's probing question into the conversation as your own turn
  instead, if you'd rather have it answered there. When the probe lands on
  something you simply don't know, **❓ bank it** parks that question in your
  global question bank and leaves the thread running — no model call, no
  breaking off; answer it whenever you like. It reads **✓ banked** once it's
  in, so you can't file it twice. A clean explanation comes due
  again on a spaced ladder (3d → 7d → longer), surfaced as a **🗣 explain
  again** nudge beside the review button — re-explaining just before you'd
  forget is the strongest rehearsal there is. The 🔊 (or **s**) reads the
  feedback aloud, your latest explanation of each conversation lands in
  both exports under *Explained back*, and **📊 progress** counts attempts,
  clean explanations, and what's due another pass. Each tree also
  gets **📝 my notes** — a space for your own synthesis of what you learned,
  written in a small **markdown** subset that **formats itself as you type** —
  type `## ` and the line becomes a heading there and then, close a `**` and
  the word goes bold. The markers stay on screen, dimmed, the way Bear and iA
  Writer do it, so nothing reflows out from under your cursor and what you see
  is exactly what gets saved. A toolbar covers headings, bullet and numbered
  lists, quotes, **bold**, *italic*, underline and `code` (Ctrl+B/I/U/H), with
  its own undo (Ctrl+Z). It
  autosaves as you type — and again the moment the tab is hidden, unloaded, or
  the box closed, so nothing is lost to a phone evicting the tab — then syncs
  with the tree and heads every export, where the markup renders properly
  rather than showing its syntax. **Shift+N** opens it. You
  can also **ask the tutor yourself** under any conversation — your question
  is answered with the node's context and stored as your own turn
  (`user: true`), which the simulated learner never sees. Two **❓ question
  banks** catch the ones you don't want answered mid-read, jotted the same
  way (a small bar, no dialog, no lost scroll position) but answered
  completely differently. Press **q** anywhere — no tree needs to be open —
  for the **global** bank: **investigate** one later and it starts a
  brand-new investigation with its own text as the topic, exactly as if
  you'd typed it into the topic box and pressed **new**. Press **Shift+Q**
  while reading for the **local** bank, tagged to the turn you were on: the
  **❓ questions** button in the conversation header opens it for that tree —
  **investigate** any one on its own, or **run all** to queue every pending
  question in one pass, exactly like `full` queues its follow-ups; either
  way it's the same single question straight to the tutor as asking
  yourself, just saved for later instead of interrupting the moment.
  A local question can change its mind: **↗ promote** moves it to the global
  bank, for when something you jotted mid-read turns out not to be about that
  passage at all but a topic in its own right — it stops being one question to
  this tutor and becomes its own investigation, carrying the profile of the
  tree it came from. The local bank folds it away under *↗ moved to the global
  bank*, so you can still see where it went.
  In the global bank, **✨ suggest questions** reads what you've banked and
  proposes a few it implies but you never wrote down — the prerequisite
  underneath them, the obvious next step past them, the case they all quietly
  assume. They arrive as proposals in a dashed panel: **+** keeps one, **✕**
  throws it away, and nothing reaches the bank (or the sync, or an export)
  until you say so.
  Either bank, once two questions are waiting, offers **⇅ order by
  dependency**: one cheap model call sorts them into the order they're best
  learned in — where two touch the same idea, whichever the other one needs
  answered first goes first, and unrelated ones keep roughly where they were.
  The ordering sticks, and travels and syncs like everything else.
  Answered ones fold under a disclosure with a jump back to what they
  became, in both banks. Conversations
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
`many`, `seeplusplus`.

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
  **read-only** tools (`view`, `grep`, `glob`, `skill` — never shell, write, or
  web) with file access from your home directory down, plus its normal
  `AGENTS.md`/custom instructions and whichever of your own MCP servers you
  turn on — so when a question touches material you have on disk, your
  team's Confluence, or anything else your Copilot setup already knows, it
  can go look. The learner, glossary, and quiz roles run with no tools and
  no custom instructions at all — they're a fixed roleplay, not a coding
  assistant.
- **The tutor can start from a past Copilot session.** When you leave an
  interactive `copilot` session it prints the id you'd resume it with; paste
  that into **⚙ local settings** (a unique prefix is enough, or the name you
  gave it with `/rename`, or just pick it from the list of recent sessions
  right there — labelled with the name, folder, size, and opening question).
  **You don't have to leave the session first:** the CLI writes each turn out
  as it happens, so a session you're in right now is already in that list, and
  an anchored session that's still going keeps up — every tutor reply re-reads
  it, so what you covered a minute ago is already known here. The **learner**
  gets something different and deliberately thinner: a generated *orientation
  brief* — the names in play and what kind of thing each one is, never the
  explanations — so it recognises your vocabulary instead of misreading a term
  and aiming the whole investigation at the wrong thing, while staying as
  ignorant of the actual answers as it has to be to ask good questions and everything you worked through
  in it — a codebase you explored, a design you argued out — is already known
  to the tutor, so you can ask about it here without setting it up again. The
  **whole session** goes over, not a summary of it — the panel tells you its
  size and says plainly that all of it is going (set
  `LEARN_SESSION_MEMORY_MAX` if you'd rather cap it, and it says so when that
  cap bites). The session's transcript is **read, never written to**: your
  session is left exactly as you left it, and nothing is chained or appended,
  so the tutor starts from the same point every turn. Tutor only — the
  simulated learner and the glossary never see it.
- **⚙ local settings** (header, local mode only) lets you swap the model per
  role (a dropdown of common ones, or type any exact id) and pick a reasoning
  effort, name one project directory of your own code or notes for the tutor
  to check first, anchor the past Copilot session above, and turn on whichever
  MCP servers you've already registered with the Copilot CLI — a checklist read straight from `copilot mcp list`,
  not a second place to define one. A one-click **+ set up confluence** runs
  `copilot mcp add` for [Atlassian's official remote MCP
  server](https://mcp.atlassian.com/v1/mcp/authv2) (Jira + Confluence Cloud;
  first use opens a browser tab to sign in, no token to type in) on your
  behalf; anything else you register yourself with `copilot mcp add` shows up
  in the checklist the same way. Model/effort/directory/anchored-session/
  enabled-servers save to `local_settings.json` next to your knowledge folder
  and apply to the next reply, no restart — and only ever exist in this local mode, never in
  the hosted deployment.

Options: `--port` (default 8577), `--dir` for the knowledge folder,
`--no-open` to skip the browser. Env knobs: `LEARN_COPILOT_MODEL` (or
per-role `LEARN_COPILOT_LEARNER_MODEL` / `_TUTOR_MODEL` / `_GLOSSARY_MODEL`)
to pin a model instead of `auto`, `LEARN_EFFORT` for reasoning effort on
models that support it, `LEARN_SESSION_MEMORY_MAX` to cap how much of an
anchored Copilot session becomes tutor memory (default: no cap — all of it),
`LEARN_TIMEOUT` per call, `LEARN_COPILOT_EXE` if the
CLI lives somewhere unusual — all of these are the *defaults* the ⚙ local
settings panel overrides once you save anything there. `python -m
learn_with_claude.localweb` works without installing the `learn` command.

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
  personas.py                 # learner/tutor prompts + root & branch message templates
  simulator.py                # run_conversation() — the reusable learner<->tutor loop
  knowledge.py                # Node + KnowledgeTree: persistence, navigation, render, md export
  export_html.py              # dyslexia-friendly HTML export (font switcher + accessible CSS)
  repl.py                     # the interactive knowledge shell
  render.py                   # dyslexia-friendly terminal formatting / colour / Windows UTF-8
  cli.py                      # argument parsing & dispatch
  webapi.py                   # the /api route handlers, shared by both web backends
  copilot_backend.py          # GitHub Copilot CLI as a model transport (local web app)
  local_settings.py           # ⚙ local settings: models/effort/project dir/MCP servers
  copilot_sessions.py         # reads past Copilot CLI sessions (tutor memory)
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
- The tutor is a *conceptual* tutor, deliberately terse to force granular
  learning. In the CLI it gets no tools at all: both personas run with the
  built-in tools disabled and `--strict-mcp-config`, so your globally
  registered MCP servers are never exposed to them. (`learn --web` is the one
  exception — see [Local web app](#local-web-app-no-keys--github-copilot).)
- The learner is a simulation of a plausible human, not a specific person; runs are
  non-deterministic.
