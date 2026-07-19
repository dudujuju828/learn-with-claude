# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

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
