# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

---

## Feature 10 — Dismiss a loose thread

### What it is
Every chip in the **loose threads** list ("words the learner flagged but
never chased") gains a **✕** — *not interested*. The term drops off the list,
the dismissal is stored on `tree.dismissed` (lowercased terms), persists,
and syncs with the tree (mirrored last-write-wins when the local copy is
newer, like note/quiz/profile — so a restore actually sticks across devices).
An **↩ n dismissed** link under the chips brings them all back; if every
thread is dismissed the section stays visible just to offer the restore.

### Why this one
- Loose threads is an advertised feature ("the tree shows where it wants to
  grow"), but it had no way to disagree with it. The learner flags plenty of
  words you genuinely don't care to chase, and they squat in the list
  forever — eight slots, so noise crowds out threads you *would* chase.
  Being able to prune the frontier is what makes the frontier useful.
- Small and pattern-shaped: one array on the tree, one merge rule following
  the existing saved_at-gated block, two small functions, and the chip UI it
  extends already exists.

### Candidates rejected (this cycle)
- **Drag-and-drop `.know.json` import** — nice desktop convenience for
  CLI↔web movers; noted for a future cycle.
- **Persist per-node reading positions across reloads** — `nodeScroll` is
  in-memory only; small comfort, smaller value.
- **PWA app-icon badge with the due-card count** — only visible for
  installed PWAs; niche.

---

## Feature 9 — Highlights travel: kept in the file, shown in exports

### What it is
Two halves of one promise — "each tree is a single portable file":

1. **The Python `KnowledgeTree` no longer strips web-side fields.** It now
   carries `highlights` as a first-class field, and preserves *any* top-level
   key it doesn't recognise (quiz, profile, survey, saved_at, whatever a
   future version adds) verbatim through `from_dict` → `to_dict`. Before
   this, opening a web-made `.know.json` in the CLI and saving silently
   deleted your highlights, quiz, and profile — data loss with no warning.
2. **Both exports show your highlights.** The Markdown export adds a
   `> ★ I highlighted: …` quote under the turn each passage came from, and
   the standalone HTML reading page adds a matching "★ I highlighted" block
   with the passage in a theme-aware highlighter band. No highlights, no
   section — exports of untouched trees are unchanged.

### Why this one
- It repairs an actual (if quiet) data-loss bug in the product's core
  portability story, and it closes the export gap NOTES has carried since
  Feature 5 ("highlights in the export… could be added later"). Your marks
  now survive every path a tree can take: sync, file, CLI, export.
- Wholly server/CLI-side Python with a real test harness
  (`tests/test_web_helpers.py` already covers the note round-trip — the
  highlight round-trip slots right beside it). No UI risk at all.

### Candidates rejected (this cycle)
- **Cross-tree highlights hub** — still parked; search (Feature 8) covers
  retrieval, exports now cover archival.
- **Node-level unknown-field preservation** — `Node` still filters unknown
  keys (turn dicts already travel verbatim, and the web adds nothing at the
  node level today); revisit only if the web ever does.
- **Archive/pin trees** — still below the line.

---

## Feature 8 — Search finds your own words

### What it is
The **search every tree** box now also matches the two things *you* wrote:
each tree's **my notes** text and every **passage highlight**. A note hit is
labelled "my notes" and opens straight into that tree's notes editor; a
highlight hit is labelled "highlight" and jumps to the marked turn (where the
passage is sitting there highlighted). Turn and glossary hits keep priority;
the 25-hit cap covers all four sources.

### Why this one
- "Search across every tree" is an advertised flagship, and it silently
  skipped exactly the words a studying user is most likely to look for —
  their own synthesis (Feature 4) and the passages they marked as mattering
  (Feature 5). Searching a phrase you *know you wrote* and getting "no
  matches" reads as a bug.
- Tiny risk: a pure extension of `searchHits` (same hit shape, same snippet
  renderer, same cap), one new click path for note hits, no storage or
  backend changes.

### Candidates rejected (this cycle)
- **Cross-tree highlights hub** — still attractive; search now covers the
  "find that passage again" need, so the aggregated browse view can wait.
- **Highlights in the Markdown/HTML exports** — the natural next parity step
  (exports already carry notes); noted for a future cycle.
- **Archive/pin trees** — organisational nicety, still below the line.

---

## Feature 7 — Read-aloud voice & speed

### What it is
The reading-settings panel gains two controls under the read-aloud toggle: a
**voice** picker (every voice the browser offers, your language's voices
grouped first, "browser default" when you don't care) and a **speed** stepper
(0.5×–2.0×, same −/+ widget as text size), plus a **▶ sample** button that
speaks a test sentence with the current settings so you can shop for a voice
without leaving the panel. Both apply to click-to-hear blocks *and* the 🔊
listen-through-a-conversation flow, persist like every other reading pref, and
reset with the panel's reset button. If the saved voice doesn't exist on this
device (voices are per-OS/browser), speech falls back to the default without
losing your choice; if the browser has no speech synthesis at all, the rows
hide themselves.

### Why this one
- Text-to-speech is a first-class aid for the app's dyslexia-focused audience,
  and until now it always used the browser's default voice at fixed speed —
  the two settings every dedicated TTS tool treats as table stakes. Readers
  who lean on TTS almost always want it faster; the default voice is often
  the worst one installed.
- Smallest risk of any candidate: pure client-side prefs (no sync, no tree
  format, no backend), and it slots into existing machinery — the `PREF_STEPS`
  stepper table, the panel row markup, and the single `speak()` choke point.

### Deliberately left out (for now)
- **The CLI's standalone HTML export** keeps its simpler read-aloud (toggle
  only). It's a share artifact with its own inline script; parity can come
  later.
- **Pitch control** — speed and voice cover the real need; pitch is a novelty.

### Candidates rejected (this cycle)
- **Cross-tree highlights list** (deferred from Feature 5) — real value, but
  reading-aid polish beats a second aggregation view this cycle.
- **Search over notes/highlights** — search today covers turns + glossary;
  worthwhile, small, noted for a future cycle.
- **Archive/pin trees** — organisational nicety; profiles already scope the
  list.

---

## Feature 6 — Rename a tree's topic

### What it is
An **✎** on each tree in the list renames that tree's topic — the display title
*and* the export filename. You could already rename a node; you couldn't fix the
tree's own title, which is fixed at creation from whatever you typed to start it
(typos and all). The rename persists, syncs, and — since the merge takes the
server's copy as its base — the local title now wins when it's newer (added
alongside the note/quiz/profile last-write-wins fields).

### Why this one
- A small but universal gap: the topic phrase you type to start a tree becomes
  its permanent title and filename, and there was no way to tidy it. Very low
  risk (a pure display/label field, no re-investigation implied), and it
  deliberately steps outside the study-suite work of the last few cycles.

---

## Feature 5 — Passage highlights

### What it is
Select a stretch of a tutor answer and a **★ highlight** action appears on the
selection chip (alongside the existing ✎ define / ⛏ dig, which now hide
themselves for longer, sentence-length selections where they don't apply). The
passage is marked with a highlighter band that **persists** — it's stored on
`tree.highlights` as `{node, turn, text}` and re-applied on every render. **Tap a
highlight to lift it.** Highlights **sync** with the tree (unioned on a merge so
a mark made on one device survives another's edits).

The re-application runs *before* the glossary-term annotation pass (and the
annotation pass now skips inside a highlight), so the two DOM rewrites never
fight over the same text — a highlighted sentence and a glossary underline
coexist in the same paragraph.

### Why this one
- Highlighting is *the* canonical study action, and this is a deliberately
  reading-first, dyslexia-friendly tool — the whole UI is built around reading
  the tutor's words carefully. Marking the sentences that matter, and having
  them stay marked across sessions and devices, is exactly the kind of thing a
  real reader reaches for.
- It builds directly on three existing patterns — the selection chip
  (define/dig), the `annotateTerms` text-node rewriter, and the sync-merge
  conventions — rather than introducing new architecture. The one genuinely
  tricky part (two passes rewriting the same text) is handled by ordering plus a
  skip rule, and the whole flow is covered by a headless test: chip behaviour on
  long vs short selections, mark rendering, coexistence with glossary
  annotation, tap-to-remove, persistence, and merge union.

### Deliberately left out (for now)
- **Highlights in the export.** They're an in-app reading aid; the Markdown/HTML
  exports carry the *content* (turns, glossary, and — from Feature 4 — your
  notes), not transient reading marks. Could be added later.
- **A cross-tree "highlights" list.** One tree at a time is enough for v1.

### Candidates rejected (this cycle)
- **Star whole answers** — a lower-risk cousin (no text ranges), but coarser;
  sentence-level highlighting is what a reader actually wants.
- **Rename a tree's topic** — a real small gap (only nodes can be renamed
  today), but low value next to highlighting; noted for a future cycle.

---

## Feature 4 — Per-tree "my notes"

### What it is
Every tree gets a **📝 notes** button (in the conversation header and the ⌘K
palette) that opens a roomy editor for your own free-text synthesis of what you
learned — the summary, the key insight, what to revisit. It:

- stores on `tree.note`, **autosaves** on close (Esc / ✕ / backdrop / "done"),
  and shows a live word count;
- **syncs** across devices with the tree (last write wins by `saved_at`, and the
  glossary/quiz merge path was extended to carry the note);
- **heads every export** — a "My notes" section is emitted at the top of both the
  Markdown and the standalone HTML export (`KnowledgeTree` now carries `note`
  through `from_dict` / `to_dict`, and both exporters render it);
- shows a **● indicator** on the button once a note exists.

### Why this one
- It's the one place the learner puts things in *their own words*. The
  "generation effect" — that you remember what you produce far better than what
  you merely read — is one of the most robust findings in learning science, and
  the app had no surface for it: every other artifact (turns, glossary, quiz) is
  machine-generated. This closes that gap and is exactly the kind of thing a
  real user keeps coming back to.
- Contained and consistent: it reuses the modal / Esc / focus-trap plumbing and
  the sync-merge conventions, and the export change is a small, tested addition
  to the two exporters. The Python round-trip test now asserts the note
  survives `to_dict` and appears in both exports (and that an absent note adds
  no section).

### Candidates rejected (this cycle)
- **Passage highlights** — high value for a reading-first tool, but persisting
  and re-applying highlight ranges over re-rendered answers (and reconciling
  them with the existing glossary underlining pass) is genuinely fiddly; a
  future cycle.
- **Pin/favourite trees** — a nice list-ordering convenience, but lower value
  than a first-class place for your own synthesis.

---

## Feature 3 — Fix a flashcard while you review it

### What it is
On the answer side of a review flashcard there's now an **✎ edit** action
(beside "↪ where I met it"). It swaps the definition for an inline textarea —
correct the wording, **save**, and you're back on the same card with the graded
intervals intact; the fix is written straight to the glossary entry (stamped,
like Feature 2, so it survives sync) and updates the conversation underlines and
exports when the session closes. Esc cancels the edit without leaving review;
grading is disabled while the editor is open so you can't mis-grade.

### Why this one
- The review screen is exactly where you *notice* a definition is wrong — you're
  staring at it, testing yourself against it. Anki's in-review "Edit" is one of
  its most-used buttons for this reason. Feature 2 made definitions editable in
  the glossary list; this closes the loop by putting the same fix where the
  friction actually surfaces.
- Very low risk and high reuse: it rides on Feature 2's save-and-stamp path and
  the existing review state machine, adding one boolean (`review.editing`) and a
  render branch. No backend change, no new dependency, no new scheduling
  semantics — a saved edit doesn't reschedule the card.

### Candidates rejected (this cycle)
- **Undo toast for deletions** — re-examined and dropped: `deleteTree` and
  `removeBranch` already gate on a native `confirm()`, so there's no silent
  data-loss gap to close, and undoing a tree deletion tangles with the sync
  tombstone protocol.
- **Review across all profiles at once** — profile-scoped decks are a
  deliberate design ("each interest keeps its own flashcards"); a power-user
  option, not a broad win.
- **Combined Anki export for a whole profile** — nice-to-have, but the in-app
  review already serves the retention loop; lower marginal value.

---

## Feature 2 — Editable glossary definitions

### What it is
Any defined term in the glossary now has an **✎ edit** action that opens an
inline textarea to rewrite its definition. The corrected text flows straight
into the flashcard review, the markdown/HTML export, and the Anki export — the
same machinery the auto-generated definition already fed. Save/cancel, Esc to
cancel, works in both the single-tree and "all trees" glossary scopes.

The edit is **stamped** (`entry.edited`), and the cross-device sync merge was
updated to prefer the newer stamped edit — otherwise the old merge rule
("a definition beats none") would silently drop a hand-edited definition when
the server already had one. Legacy behaviour (no stamp) is unchanged.

### Why this one
- Definitions are written by a cheap model (`haiku`, effort `none`) the moment a
  term appears, so they're a serviceable *first draft* — sometimes too generic,
  occasionally off. Because they become the answer side of spaced-repetition
  flashcards, a wrong definition means you rehearse wrong information. Letting
  the user correct/personalise it is squarely on the learning path.
- Low risk, high reuse: it's a small, self-contained addition to the existing
  glossary entry UI (mirrors the "define it" / "forget" actions), stores nothing
  new except an optional timestamp, and needs no backend change. The only
  non-trivial part — making an edit survive a sync conflict — was fixed in the
  one merge function and verified against four cases.

### Candidates rejected (this cycle)
- **Undo toast for deletions** — genuinely useful safety, but restoring a
  tree that was already tombstoned + pushed to the server is fiddly and touches
  the sync protocol; higher risk than it looks.
- **Typed-recall review mode** — auto-grading free-text definitions is
  unreliable; the established self-grade paradigm already covers recall.
- **Bulk profile assignment** — organisational nicety, lower marginal value
  than fixing wrong flashcard answers.

---

## Feature 1 — Progress dashboard (spaced-repetition + quiz stats)

### What it is
A read-only **📊 progress** panel (a modal, like quiz / review / survey) that
turns the learning data the app already collects into an at-a-glance view,
scoped to the active profile the same way the review deck is:

- **Headline tiles** — cards (defined terms), due now, trees, investigations.
- **Recall strength** — a stacked bar splitting your cards into *new* /
  *building* / *solid* by their spaced-repetition interval, so you can see how
  well-established your knowledge base actually is.
- **Coming up** — a 14-day forecast bar chart of how many cards fall due each
  day, so you can plan review load ahead.
- **Habit** — current review streak (consecutive days with at least one graded
  card) and whether you've practised today.
- **Quizzes** — attempts, average and best score across the profile, plus the
  last few results.

Reachable from a button in the *words* section and from the ⌘K command palette;
closes with Esc, traps focus, works on mobile — all via the existing modal
infrastructure.

### Why this one
- **Highest value / lowest risk.** The app is fundamentally a spaced-repetition
  learning tool (glossary → scheduled review) plus quizzes, but it has no place
  that shows momentum, retention, or upcoming load — the single most-used screen
  in tools like Anki. All the data already exists (`entry.rev` with
  `ivl`/`due`/`last`/`n`, `tree.quizzes`, profiles); nothing new needs storing.
- **Purely additive & self-contained.** No backend changes, no new dependencies,
  no change to any existing code path — it only *reads* the store. It reuses the
  established modal pattern (`quizbox`/`reviewbox`/`surveybox`), the palette, the
  Esc/focus-trap plumbing, and the theme variables, so it can't regress current
  behaviour.
- **Genuinely useful, not flashy.** The forecast is actionable planning; the
  maturity split answers "how solid is what I know"; the streak drives review
  adherence, which is what actually makes spaced repetition work.

### Candidates rejected
- **Tags on trees** — real value for organisation, but *profiles* already group
  trees, and tags would have to thread through sync/merge/render/export. Higher
  risk, overlapping value.
- **Combined cross-tree glossary index** — largely already covered by the
  glossary's "all trees" scope and the cross-tree search; low marginal value.
- **Freeform notes on a node** — overlaps with the existing "ask the tutor
  yourself" and "dig" turns (user-authored turns already exist).
- **Review calendar heatmap** — a strict subset of this dashboard; folded in as
  the streak + forecast instead of a separate, heavier feature.
