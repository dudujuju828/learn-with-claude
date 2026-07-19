# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

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
