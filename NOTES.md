# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

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
