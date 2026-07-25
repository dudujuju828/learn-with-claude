# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

---

## Feature 31 — search forgives your spelling

### What it is
The flagship **search every tree** — and the glossary filter, and ⌘K —
now forgive the way the ⌨ type checker always has. Exact matches behave
exactly as before; only when a query finds *nothing* does a second pass
run, where each query word may land as a substring **or** as a word
within typo distance (nothing under 4 letters, one edit to 7, two from
8 — an adjacent swapped pair, the classic dyslexic slip, counts as
one), and word order stops mattering. The results say so — *"nothing
spelled quite like that — close matches:"* — and the snippet marks the
word that actually matched, so "collission" finds collision,
"idempotancy" finds the glossary entry, "amortised analyzis" finds your
own note, and "chaining separate" finds the phrase it reverses. Garbage
still honestly finds nothing.

### Why this one
- For a dyslexia-focused tool, exact-substring search was precisely the
  wrong matcher: misspelling an unfamiliar technical term is the normal
  case for the stated audience, and the failure lands on the app's
  advertised flagship ("search across every tree") as a flat, wrong "no
  matches" — for content the user *knows is there*. Feature 20 already
  established the principle (a typo or swapped pair reads as *close*,
  not wrong) and built `editDist`; this carries the same forgiveness to
  the retrieval surfaces. Feature 8's log even flagged the stakes:
  searching a phrase you know you wrote and getting nothing "reads as a
  bug".
- Contained by design: the exact pass is byte-for-byte unchanged and
  always wins; the fuzzy pass only exists where the old behaviour was
  a dead end, so no existing result set can regress. One matcher
  (`findHit`) threads through all four search sources, the palette, and
  the glossary filter; `typedVerdict` now shares the same `typoSlack`
  rule instead of duplicating it.
- Verified with an 11-assertion headless run: exact-no-hint, typo,
  swap-in-phrase, reversed word order, glossary, notes, garbage,
  short-word strictness, palette fallback, and the typed-recall
  verdicts unchanged.

### Candidates rejected (this cycle)
- **FSRS-style scheduling upgrade** — a real algorithmic improvement,
  but it rewrites the schedule data the whole retention loop rests on,
  is hard to verify honestly, and the simple ladder is a deliberate
  design ("Anki-ish, without the ease bookkeeping").
- **Listen through a whole tree** (chain conversations into one audio
  queue) — a small extension of listenNode; parked until the drill
  proves how much hands-free listening actually happens.
- **Dictated notes/questions** — speech recognition is still
  Chromium-only; parked with its cousins.

---

## Feature 30 — 📅 today: the docket

### What it is
A **📅 today · n** button in the words tab (and *today* in ⌘K),
appearing whenever something is waiting: one modal listing everything
*actionable* across the active profile — **🔁 review** (cards due, with
a note when the 🎧 drill will run them), **🗣 explain again** (each due
conversation listed by name, not just a count), **⛏ loose threads**
grouped by tree — from *every* tree, not just the open one — each chip
chasing straight into the branch UI with the term prefilled, each ✕
dismissing it (the same `tree.dismissed` store, now writable
cross-tree), and **🗺 uncovered ground** (survey maps with unexplored
foundations, one tap from the map). Empty docket → the button hides;
opened empty via ⌘K → "all clear". Esc, backdrop, focus trap, print
hide — the highlights-hub skeleton throughout.

### Why this one
- The audit found the app's nudges scattered *and scoped
  inconsistently*: review and explain-again are profile-wide buttons,
  but loose threads and survey coverage were only visible for the
  currently-open tree — the cross-tree frontier was invisible. A
  half-covered survey in a tree you haven't opened this week simply
  never spoke up. The docket is the missing profile-level answer to
  "what should I do right now?" — the same decision-cost argument that
  justified → next (Feature 24) at tree level, applied to the daily
  session: open the app, open today, work the list.
- Pure aggregation over existing data — `dueCards`, `teachDueList`,
  `looseThreads`, `surveyCovered` all existed; zero model cost, no new
  storage, no sync changes (the one write, cross-tree dismissal, rides
  the existing `dismissThread` with an optional treeId).
- Verified with a 17-assertion headless run over two seeded trees:
  counts, all four jump actions (deck, teach modal, survey map, branch
  UI with the term prefilled), cross-tree dismissal persisting to the
  right tree, and the Esc chain.

### Candidates rejected (this cycle)
- **Onboarding demo tree** — a bundled pre-grown tree for the empty
  state; real for a new user, but the example-topics row already
  seeds the cold start, and this app's user is past it.
- **Cross-tree glossary linking** (a term defined in tree A underlined
  in tree B) — real idea, but it blurs the "each tree is a portable
  file" boundary and the payoff is unclear.
- **Stale-tree resurfacing** ("you haven't touched X in 14 days") —
  guilt-trip noise; the docket lists work that's actually *due*.

---

## Feature 29 — 🎧 hands-free drill: the review deck runs itself, out loud

### What it is
A **🎧 drill** toggle in the review header (the **d** key; *hands-free
drill* in ⌘K). While it's on, the deck drives itself: the term is
spoken, a recall pause follows — its length set by a ⏱ stepper right in
the header (2–12s), made visible as a thin bar filling under the card —
then the term and answer are spoken together, and after a beat the card
is marked **good** and the next one begins. The screen is held awake
(Wake Lock, progressive) because this is a look-away mode. Your hands
stay free but keep the last word: **1–3** grades a card yourself at any
moment, **Space** shows the answer early, **↩ / u** takes a grade back —
and then the drill *waits* for your hand-picked verdict before rolling
on — ✎ edit pauses it, **d** or the toggle stops it. Leaving the tab and
coming back restarts the current card instead of stalling. Scheduling
semantics are untouched, an "again" card still comes back inside the
session, and the summary owns up to every grade the drill gave itself
("the 🎧 drill marked 7 good — ↩ takes back the last one if it deserved
again"). 🎧 and ⌨ type are opposites (one asks for your hands, the other
frees them), so turning one on turns the other off.

### Why this one
- The most-parked candidate in this log — deferred in Features 17, 18,
  19, 21 and 23, always with the same note: "attractive for the audience
  but a real design cycle of its own (timing, auto-advance,
  background-tab speech limits)". This session was that cycle, and each
  named risk got its answer: timing is a user-set pause with a visible
  bar; auto-advance follows Anki's auto-advance precedent (default
  *good*, any key overrides, undo holds the loop); background-tab limits
  are handled by restarting the card's phase on `visibilitychange` plus
  a wake lock so the phone never sleeps mid-drill.
- It completes the audio story the app has been building for its
  dyslexic audience since Feature 7 (voice/speed), 17 (karaoke), 19
  (spoken cards), 22 (spoken quiz): every surface could *speak*, but
  review — the daily loop — still demanded eyes and fingers for every
  card. Now the deck can run while you walk.
- Zero model cost, no backend, no storage or sync changes: two pref
  keys, one reactive loop re-armed by `renderReview` (every state change
  already funnels there), and a token that quietly retires callbacks
  from a phase that's no longer current.
- Verified end-to-end in headless Edge with a stubbed speech engine:
  22 assertions across the whole lifecycle (auto-reveal, auto-grade,
  schedule write, undo-hold, manual release, requeue, summary
  disclosure, wake-lock release, toggle-off).

### Candidates rejected (this cycle)
- **Mermaid diagrams in web tutor answers** — the CLI's diagram story on
  the web, but it's a heavy client dependency plus model-generated
  syntax that fails unpredictably; wrong risk profile.
- **Voice-answered review (speech *recognition*)** — still
  Chromium-only and flaky offline; parked with its cousins.
- **Notification-based review reminders** — permission-heavy and
  PWA-scoped; the tab title + icon badge (Feature 13) already carry the
  nudge.

---

## Feature 28 — explain it back grows into the full Feynman loop

### What it is
The session's brief: pick one feature and improve it relentlessly. The
pick was **🗣 explain it back** — it *is* the app's purpose (understanding
that sticks, in your own words) — and four rounds took it from a one-shot
feedback box to a complete practice loop:

1. **Verdicts and the retry loop.** Every reading now ends in an honest
   verdict — **✓ clean** (nothing important missing), **≈ close** (the
   one gap matters), **△ gappy** — with a consistency rule wired into the
   prompt (if "missing" says complete, the verdict must be clean; judge
   generously on wording, strictly on ideas). Feedback under a verdict
   guides the loop: *aim at the gap — edit your words above and send
   again.* Every attempt keeps its verdict; a trail of chips (△ 1 ≈ 2
   ✓ 3) shows the explanation getting cleaner, tapping one revisits its
   words and feedback, and the header button badges the best verdict
   (🗣 explain ✓ · 3). The modal opens with an *empty* box on purpose —
   fresh recall beats editing old words — but revisiting an attempt seeds
   a refinement.
2. **Spaced re-explanation.** A clean explanation comes due again on a
   3d → 7d → ×2.5 ladder (the card ladder's shape); anything less is due
   tomorrow. Entirely *derived* from the attempts' dates and verdicts —
   no new storage, nothing to sync or migrate. Due conversations surface
   as a **🗣 explain again · n due** nudge beside the review button (and
   in ⌘K), which drops you straight into the due conversation's modal.
   Re-explaining just before you'd forget is the spacing effect applied
   to concepts, where the app previously spaced only terms.
3. **Feedback that closes the loop.** **⤳ chase it** sends the tutor's
   probing question through the existing ask-the-tutor path — the answer
   lands in the conversation as your own turn, so the feedback's open
   thread actually gets chased. The 🔊 (and the **s** key) reads the
   feedback aloud through the existing karaoke machinery.
4. **Visibility.** Both exports gain an **Explained back** section — the
   latest attempt per conversation, verdict-tagged, with the gap that
   mattered (Python `teach_map()`, orphan attempts skipped, covered by
   the round-trip test). **📊 progress** gains an *explained back*
   section: conversations explained (n/m), clean count, due another pass.

### Why this feature
- Generation + feedback + spacing + closure is the complete rehearsal
  cycle learning science asks for, and every round lands on a different
  leg: verdicts make feedback *actionable* (F25's cards were a read-once
  artifact), the ladder makes explanations *recur* (the single strongest
  intervention available), chase-it turns feedback into the next
  learning step, and the exports/stats make the practice visible.
- Every round rides existing machinery: the verdict is one JSON key, the
  schedule is derived, chase-it is `askThunk`, the audio is `speakBlock`,
  the stats tile helper and export patterns already existed.

### Candidates rejected (this cycle)
- **Auto-grading the schedule from verdicts into `entry.rev`** — teach
  attempts are conversations, not glossary terms; forcing them into the
  card scheduler would tangle two clean systems.
- **Voice-dictated explanations** — still Chromium-only; parked with its
  cousins.
- **Diffing attempts** (highlight what changed between attempt 1 and 2)
  — cute, but the verdict trail already tells the improvement story.

---

## Feature 27 — the gaps interview: ask, listen, probe, then map

### What it is
Feature 26's one-shot "write down what you know" box grows into what a
real tutor does: a **back-and-forth interview** (the session's brief).
The opening question is fixed and free — *what do you already know about
X, and where have you met it?* — and from your first answer the model
takes over, one short question per turn, following what each answer
reveals: testing a belief that sounds off, pushing on the edge of what
you seem to know, sampling a load-bearing area you didn't mention.
"No idea" is explicitly a good answer (the prompt forbids making you feel
caught out, and forbids teaching mid-interview — that's the
investigation's job). It stops the moment another answer wouldn't change
the read — usually 3–5 questions, hard-capped at 6 server-side — or when
you press **that's enough — map me**. The same solid/shaky/gaps map then
appears and the investigation starts exactly as before; `tree.baseline`
now keeps the whole transcript as its `text`, so 🧭 baseline replays the
interview alongside the map.

### Why this one (and why the redesign is right)
- Elicitation beats recall-dumping: people don't volunteer what they
  don't think to mention, and a single written account can't be probed.
  Adaptive questioning is how diagnostic assessment actually works — each
  question lands where the previous answer left uncertainty, which is
  precisely what a static textarea cannot do.
- The route is a clean generalisation, not a second system: `interview`
  either returns the next `question` or the final `assessment` (same
  shape Feature 26 defined, same `_clean_assessment` validation, same
  `gaps` conversation kind downstream — thunk, resume, merge, and chip
  all untouched). The transcript is rebuilt as proper multi-turn
  messages, the way the learner route already replays its history.
- Cost stays honest: the fixed opening question is free, each answer is
  one visible model call, and the interview's total lands on the root
  node like the old single call did.

### Candidates rejected (this cycle)
- **Keeping the one-shot box as a second path** — the interview subsumes
  it: dump everything into answer one and the tutor simply concludes
  early.
- **Voice-answered interview** — the natural pairing for this app's
  audience, but speech *recognition* is a new platform capability
  (SpeechRecognition is Chromium-only and flaky offline); parked
  alongside the audio review drill.

---

## Feature 26 — 🧭 gaps: the investigation starts from what you already know

### What it is
A fourth start button beside new / full / survey: **gaps**. Type a topic,
press it, and instead of launching cold you're asked what you already
know — or think you know — about it (rough and honest beats polished).
One model call sizes you up into three cards — **✓ solid** (won't be
re-explained), **△ shaky** (beliefs that are off, echoed in your own
wording so you recognise them), **○ the gaps** (the load-bearing things
you didn't mention) — plus your evident learner level and the one concept
the first investigation should target. Press again to start: the learner
opens at your diagnosed level with the map in hand ("do NOT re-ask what
you have solid; where you are shaky, check your belief against the
tutor"), the tutor is told never to re-explain the solid and to correct
the shaky explicitly when touched, and the whole thing aims at the
biggest gap first. The map lives on `tree.baseline` (LWW-merged like
survey, extras round-trip through the CLI, **🧭 baseline** in the header
reopens it), a resumed root rebuilds the same gaps context, and editing
your words after a read invalidates it — you re-run the sizing before
starting.

### Why this one
- The brief asked for a new start-mode button that's genuinely meaningful.
  The strongest learning principle with no surface anywhere in the app is
  Ausubel's: "the most important single factor influencing learning is
  what the learner already knows — ascertain this and teach accordingly."
  Feature 12's log already conceded the flows assume you start from zero
  ("the survey flow assumes you start from zero, but its own learner
  picker admits you often don't") — know-it patched that for survey
  *coverage*, but nothing ever ascertained what you know and taught
  accordingly. Prior-knowledge activation, misconception elicitation
  (straightening a wrong belief beats never surfacing it), diagnosed
  rather than self-picked learner level, and a calibration moment (seeing
  your own knowledge mapped) — one button, four principles.
- Complements rather than overlaps: survey maps the *topic*, gaps maps
  *you*; full tours forward, gaps starts honest. Teach-back (F25) is the
  same muscle at the end of learning; this is it at the start.
- Pattern-shaped everywhere: the modal is the teach-back plumbing (CSS
  extended by comma), the thunk is rootThunk plus a stored map, the
  seeding is a fourth `kind` beside root/branch/followup, the route is
  one prompt + one handler (and the vercel.json rewrite the log warns
  about).

### Candidates rejected (this cycle)
- **compare mode** (two topics side by side, analogical encoding) — real
  principle, but "X vs Y" already works typed into `new`, and the input
  shape (two fields) fights the one-topic row.
- **case mode** (worked example first, then abstract) — closer to a tutor
  style than a start mode; a custom tutor can already do it.
- **Hands-free audio review drill** — parked a fourth time.

---

## Feature 25 — 🗣 explain it back: the Feynman step

### What it is
A **🗣 explain** button on any conversation with tutor answers (and
*explain it back* in ⌘K): a modal where you explain what the conversation
taught you in your own words, as if teaching a friend. One tutor call
reads it against the conversation's digest (the ground truth) and answers
with three cards — **✓ what's solid** (specific, echoing your phrasing),
**△ the gap that matters** (the ONE most important missing or wrong
thing, never a list), **? to chew on** (one probing question). Feedback
is about ideas only; the prompt forbids mentioning spelling, grammar, or
style — for a dyslexia-focused tool that's non-negotiable. Attempts live
on `tree.teach` (unioned on merge like highlights, so attempts from two
devices both survive), travel in `.know.json` via the extras round-trip,
and reopening shows your last attempt so you can watch your explanation
improve; the header button counts them.

### Why this one
- The deepest untapped learning principle in the app. Its core conceit is
  watching a *simulated* learner learn; the human's own production
  surfaces were free-form (notes — write-only, nobody reads them back) or
  single-term (typed recall). Self-explanation with formative feedback —
  the Feynman technique — is among the best-supported effects in learning
  science, and it attacks the same self-deception Feature 20 did, one
  level up: terms were covered, *concepts* weren't. Your explanation is
  checked against what was actually covered, which is exactly where the
  illusion of competence lives.
- The Feature 2 objection ("auto-grading free text is unreliable")
  doesn't apply: nothing is graded and nothing is scheduled — the call is
  a feedback call, the thing a model is actually good at, anchored to the
  digest.
- Pattern-shaped: digest machinery existed, modal plumbing cloned from
  notes, merge rule cloned from highlights, one new prompt + one route
  (and the vercel.json rewrite the log warns about).

### Candidates rejected (this cycle)
- **Hands-free audio review drill** — parked a third time; still a full
  design cycle of its own.
- **Teach-back graded into review scheduling** — deliberately not: grading
  free text is the known trap; feedback, not a grade.
- **Explanations in exports** — the attempts travel in the file already;
  rendering them in exports can follow if the surface earns its keep.

---

## Feature 24 — → next: the tutor picks what to learn next, on any tree

### What it is
A **→ next** button in the conversation header (and *what's next?* in ⌘K):
one press has the tutor review everything the tree has covered and pick
the ONE concept that best builds on it — preferring a why/how/when/what-if
angle over another "what is" — then a follow-up investigation runs on it,
seeded with the full recap so the learner continues instead of restarting.
It is exactly the step `full` chains four of, now available on any tree at
any moment: after a `new`, at the end of a `full` tour, on a half-covered
survey tree. The tutor's one-sentence *why* is no longer thrown away: it
is kept on the node (`why`), shown in the new conversation's crumb,
carried by the Python `Node` so a CLI round-trip keeps it, and the CLI's
own `full` sessions now store it too. The button turns primary when the
current conversation is done — the exact "what now?" moment.

### Why this one
- The brief asked for the next-best feature grounded in learning
  principles; this one operationalises three at once. **Building on prior
  knowledge**: the pick must connect to what was covered (prompt-enforced,
  recap-seeded — the follow-up learner starts warm, not from zero).
  **Elaboration over accumulation**: the picker prompt forces a different
  kind of question — why it works, when it fails, how it compares —
  instead of stacking a third "what is" on the pile; recognition and
  recall practice already exist (quiz, review), but nothing pushed
  *deepening*. **Momentum in self-directed learning**: "what should I
  learn next?" is where self-paced learners stall; a guided next step at
  zero decision cost keeps the loop going, and the surfaced *why* is a
  small metacognitive cue — you see the shape of the frontier, not just
  the next stop.
- Feature 11-style existence check first: the machinery existed
  (`next_concept` endpoint, `followupThunk`) but was reachable **only** by
  committing to a 4-investigation `full` run at creation time. Branch
  needs you to pick the turn yourself, loose threads only chase flagged
  words, survey only covers the mapped foundations — no surface asked the
  tutor "where to, from here?" on a living tree.
- Tiny surface: one header button + `cmdNext()` reusing `followupThunk`
  verbatim, a `why` stash where the pick already landed, one dataclass
  field for round-trip parity, palette/help/README lines.

### Candidates rejected (this cycle)
- **Hands-free audio review drill** — still a full design cycle of its own
  (timing, auto-advance, background-tab speech limits); parked again.
- **PWA share target** — still Android-only in practice.
- **The why in exports** — it now travels in the file; rendering it in the
  Markdown/HTML exports is a natural small follow-up once it proves its
  keep on screen.

---

## Feature 23 — Read-aloud keeps the spoken word on screen

### What it is
While something long is being read aloud, the page now **follows the
karaoke highlight**: when the spoken word drifts into the bottom fifth
of the screen (or above the top), the conversation glides so the word
sits comfortably in view again. The moment you scroll, page, or arrow
anywhere yourself, following stops for the rest of that block — your
hand on the wheel always wins. It only ever operates in the
conversation (never inside modals), honours `prefers-reduced-motion`
(instant hops instead of glides), and re-arms with each new block.

### Why this one (and how the objection resolved)
- Parked in Features 17, 18 and 21 with one stated reason: auto-scroll
  "fights the user's own scrolling". The resolution is the rule every
  dedicated reading tool uses — *user input cancels following*: wheel,
  touch, or a scroll key hands control back instantly, per block. With
  that rule the conflict disappears, and what remains is the payoff:
  Feature 17's whole premise is eyes-and-ears on the same word, which
  silently breaks the moment the word walks off-screen in any block
  taller than the viewport — precisely the long blocks where a dyslexic
  reader leans on read-aloud hardest.
- Small surface: a hook where the word-paint Range is already computed,
  one viewport check, two disable listeners, `stopSpeech` clears it.

### Candidates rejected (this cycle)
- **"Define it" on a loose thread** — dead on arrival at the
  Feature 11-style existence check: every flagged term is *already*
  auto-defined into the glossary the moment it appears; loose threads
  are about unchased conversations, not missing cards.
- **Hands-free audio review drill** (speak term → pause → speak answer)
  — attractive for the audience but a real design cycle of its own
  (timing, auto-advance, background-tab speech restrictions).
- **PWA share target** — still Android-only in practice.

---

## Feature 22 — The quiz speaks: hear the question, the choices, the why

### What it is
Quizzes were the last mute surface. A **🔊** beside the quiz question
(or the **s** key) reads the question and then each choice in order,
karaoke word-painting included, in your chosen voice and speed — so a
dyslexic reader isn't decoding four dense options under test pressure
with no support. After you answer, the explanation gets its own 🔊 (and
**s** switches to it). Speech stops the moment you answer, advance, or
close; every control hides when the browser can't speak.

### Why this one
- Deferred in Feature 19 ("a natural follow-up if quizzes feel mute")
  and again in Feature 21 — read-aloud now exists on conversations,
  glossary and flashcards, which makes its absence on the *most
  reading-intense* interaction (a timed-feeling, four-options-at-once
  test) the sharpest remaining gap for the app's stated audience.
- Pattern-shaped: `speak()` + karaoke already work on any element and
  skip buttons; the one real change is wrapping each choice's text in a
  span (buttons themselves are unspeakable by design) and chaining
  speaks with the existing `onDone` callback.

### Candidates rejected (this cycle)
- **Follow-scroll for karaoke in long blocks** — still parked (fights
  the user's own scrolling).
- **PWA share target (receiving .know.json)** — Android-only in
  practice, needs service-worker POST handling; the outbound half
  shipped in Feature 18.
- **Speaking the summary's missed-question list** — same machinery, far
  colder surface; fold in later if the quiz 🔊 earns its keep.

---

## Feature 21 — Undo the last review grade

### What it is
An **↩** in the review header (and an *undo the last grade* button on
the session summary, plus the **u** key) takes back the one grade you
just gave: the card's schedule is restored to exactly what it was, an
"again" requeue is withdrawn, and you're standing back on that card's
answer side to grade it properly. One step only — it's a mis-tap eraser,
not a history — and it clears when the session closes.

### Why this one
- Grading is the single most-repeated tap in the app and the only one
  that's both instant and irreversible: on a phone the three grade
  buttons sit in a row, and one fat-finger writes a wrong interval into
  the schedule the entire retention loop depends on (a mis-tapped
  *easy* hides a weak card for days). Every serious SRS ships undo as a
  core button; checked first (Feature 11 lesson) — nothing like it
  exists anywhere in the app.
- Tiny and fully local: a one-slot stash of the previous `entry.rev`
  taken at grade time, one restore function, one header button. No new
  storage, no sync semantics (the restored state persists through the
  same `persistTree` path the grade used).

### Candidates rejected (this cycle)
- **🔊 on quiz questions** — the remaining mute surface, but quizzes are
  an occasional per-tree activity while grading happens dozens of times
  a day; parked again, next in line.
- **Profile-wide quiz stitched from cached per-tree questions** — zero
  model cost, but a mixed attempt has no natural home in `tree.quizzes`,
  and recognition testing is already served twice.
- **Undo for tree deletion** — re-examined and re-dropped for the same
  reason as Feature 3: deletion is confirm-gated and undo would tangle
  with the sync tombstone protocol.

---

## Feature 20 — Type the answer: verified recall in review

### What it is
A **⌨ type** toggle in the review deck flips the cards around: you're
shown the definition and you **type the term** it defines. The app checks
your answer itself — case, punctuation, and hyphen/space differences are
ignored, and a small typo counts as *close* (shown with the exact
spelling) rather than wrong, which matters for a dyslexia-focused tool.
The verdict (✓ / ≈ / ✗, with what you typed) appears with the revealed
term, and the matching grade button is pre-focused — but *you* still
grade, so a synonym the checker couldn't know about isn't held against
you. **skip typing** falls back to the classic flip for that card. The
choice persists like any reading pref and is remembered next session;
scheduling semantics are completely unchanged.

### Why this one
- The session brief asked for a quizzing/testing feature, and this is the
  testing loop's real weakness: both existing surfaces (per-tree quiz,
  review deck) test *recognition*, and review grades are self-reported —
  "yeah, I knew that" is exactly the self-deception spaced repetition
  suffers from. Typing the answer converts the deck into *verified
  production practice*, the strongest form of the testing effect, at zero
  model cost.
- Feature 2 rejected "typed-recall review mode" because auto-grading a
  free-text **definition** is unreliable. That objection doesn't apply in
  the other direction: the **term** is short and objective — Anki's
  type-in-answer has graded it for two decades. The earlier rejection was
  about the wrong side of the card.
- Contained and pattern-shaped: one pref boolean, one header toggle, two
  render branches inside the existing review modal, ~40 lines of check
  logic. No storage, sync, or backend changes; classic mode untouched.

### Candidates rejected (this cycle)
- **Local zero-cost MCQ over the profile's glossary** — would answer
  Feature 13's "quiz over a whole profile" objection (it was model-call
  heavy; this is free), but it's a *third* recognition surface when
  recognition is already served twice; recall is the uncovered axis.
- **Quiz misses feed the review deck** — quiz questions aren't
  term-shaped; turning a missed question into a card needs another model
  call and a new card type.
- **Per-question quiz analytics** (which questions you repeatedly miss) —
  bookkeeping, not a new practice loop.
- **🔊 on quiz questions** — audio polish parked since Feature 19, not
  testing.

---

## Feature 19 — Hear the flashcard

### What it is
Review cards can be spoken: a small **🔊** beside the term (both sides)
and beside the revealed definition reads it aloud with your chosen voice
and speed, karaoke word-painting included — and the **s** key says the
term (front) or the answer (back) without leaving the keyboard flow.
Speech stops the moment the card changes or the modal closes. Hidden
entirely when the browser has no speech synthesis.

### Why this one
- The review deck is the app's most-repeated surface, and it presents
  *unfamiliar technical terms* as bare text — for the dyslexic audience,
  decoding "idempotency" is exactly the hard part, and hearing a term
  pronounced correctly is itself part of learning it (the card even says
  "out loud counts"). Read-aloud existed everywhere in the app except
  here.
- Tiny and pattern-shaped: `speak()` (with Feature 17's karaoke) works on
  any element and already skips buttons, so the 🔊 rides the existing
  machinery; the keyboard branch slots into the review keydown block that
  already does 1/2/3 and Space.
- Checked first: review already had keyboard grading (1/2/3, Space/Enter
  flip) — this cycle's other candidate — so pronunciation was the real
  gap.

### Candidates rejected (this cycle)
- **Keyboard grading in review** — already shipped long ago; the audit
  caught it before duplicate work (the Feature 11 lesson).
- **🔊 on quiz questions** — same argument, smaller surface; a natural
  follow-up cycle if quizzes feel mute in practice.
- **Follow-scroll for karaoke in long blocks** — still parked (fights
  user scrolling).

---

## Feature 18 — Exports go through the share sheet on touch devices

### What it is
On a touch-first device (primary pointer is coarse), every file the app
saves — save .know.json, export md, export html, anki cards, and the
save-all backup — opens the OS **share sheet** instead of forcing a
browser download: AirDrop it, Save to Files, drop it in Drive, send it to
the other device where you'll keep reading. Desktop keeps the plain
download. Anything the platform won't share (unsupported type, expired
tap-activation after a slow export, no share support at all) falls back
to the download; dismissing the sheet is treated as "changed my mind",
not an error.

### Why this one
- Carried as "next in line" for two cycles. The app is explicitly
  multi-device (sync, PWA, import-by-drop), and its portability story is
  "each tree is a single file" — but on phones that file used to land in
  the browser's downloads limbo, exactly where mobile users lose things.
  The share sheet is how files leave apps on mobile.
- Smallest possible surface: all five save paths already funnel through
  the one `download()` helper, so the change is one function plus a
  `File`/`canShare` feature check. Existing desktop behaviour is
  untouched (coarse-pointer gate, not width, so a narrow desktop window
  still downloads).

### Candidates rejected (this cycle)
- **Follow-scroll for the karaoke highlight in long blocks** —
  deliberately left out of Feature 17; would fight the user's own
  scrolling in click-to-hear.
- **Voice/speed/karaoke parity in the CLI's standalone HTML export** —
  share artifact, simpler on purpose (decided in Feature 7, still holds).
- **PWA share *target* (receiving .know.json from other apps)** — the
  inbound half; Android-only in practice and needs service-worker POST
  handling; the outbound half is where the daily friction is.

---

## Feature 17 — Read aloud follows along, word by word

### What it is
While read-aloud speaks a block (click-to-hear or the 🔊 listen-through
flow), the word being spoken is highlighted in the text — karaoke-style, in
the theme's primary colour pair — so eyes and ears stay on the same word.
The standard follow-along aid every dedicated reading tool (Immersive
Reader, Kurzweil) ships, and squarely aimed at this app's dyslexic
audience: multimodal reinforcement plus never losing your place.

### Why this one (and why the risk collapsed)
- Deferred in Feature 16 as "the standout remaining accessibility
  delighter", parked only because live DOM rewriting during speech would
  fight the glossary-underline and passage-highlight passes. The **CSS
  Custom Highlight API** (`CSS.highlights` + `::highlight()`) removes that
  entire class of risk: the current word is a `Range` painted by CSS, no
  DOM mutation at all, so the three annotation systems can't interact.
  Verified working (including `var()` theme colours in `::highlight()`) in
  this machine's Edge before starting.
- Progressive enhancement at every layer: no API → no highlight (block
  outline stays); voice never fires word boundaries (some mobile/remote
  voices) → no highlight; boundary lands on text a re-render detached →
  that word just doesn't paint. Speech itself is untouched.
- The utterance text derivation moves from a DOM clone to a walker that
  builds the identical string *plus* a char→(text node, offset) map — the
  map is what turns a boundary event's `charIndex` into a `Range`.

### Deliberately left out
- **Follow-scroll within a long block** (auto-scrolling the highlighted
  word into view): fights the user's own scrolling in the click-to-hear
  case; the listen flow already centres each block. Revisit if blocks
  ever outgrow a screen.
- **The CLI's standalone HTML export** keeps its simpler read-aloud, as
  decided in Feature 7.

### Candidates rejected (this cycle)
- **navigator.share for exports on mobile** — still next in line; smaller
  value than the reading aid this app is *for*.
- **Auto theme following the OS light/dark switch live** — first visit
  already honours `prefers-color-scheme`; a live "auto" option is marginal
  next to six explicit themes.
- **CLI note/highlight commands** — the minority surface, again.

---

## Feature 16 — Rename a profile

### What it is
When a profile is active, a **✎** chip appears at the end of the profile
row: rename the interest area, and every tree filed under it is re-filed
under the new name (each stamped and synced, so other devices follow), the
active-profile preference moves with it, and renaming onto an existing
profile simply merges the two. Same prompt-based pattern as renaming a
tree's topic (Feature 6) or a node.

### Why this one
- The same stuck-state class Feature 6 fixed for tree titles: the profile
  name you first typed (typos included) was permanent — the only way out
  was re-filing every tree by hand through the per-tree picker. Profiles
  scope the tree list *and* the review deck, so people invest in them;
  investment deserves an undo for the name.
- Tiny: one function over the existing `treeProfile`/`persistTree`/LWW
  machinery, one chip in a row that already re-renders.

### Candidates rejected (this cycle)
- **navigator.share for exports on mobile** — nice flow polish; downloads
  do work on mobile; next in line.
- **Word-by-word karaoke highlighting for read-aloud** — the standout
  remaining accessibility delighter, but boundary-event→DOM mapping across
  the glossary/highlight rewrites is genuinely risky; needs its own
  focused cycle with careful design.

---

## Feature 15 — High-contrast theme

### What it is
A sixth colour theme, **contrast**: true black page, white text, and bright
accent hues, with every text pairing computed at **WCAG AAA (≥7:1)** and
every border at ≥3:1 (checked programmatically, not eyeballed: fg/bg lands
at 21:1, the weakest pair — term on its chip background — at 8.5:1). It
behaves exactly like the other themes: a swatch in the reading settings,
`color-scheme: dark` so native widgets follow, restored before first paint
by the boot script, and carried into the confidence-spark colours (the
"which themes count as dark" test is now a helper both call sites share).

### Why this one
- The app's whole identity is reading accessibility, and its five themes
  are soft-contrast by design — lovely for dyslexic glare-sensitivity,
  wrong for low-vision readers, who need the opposite: maximum contrast.
  A dedicated high-contrast theme is the standard answer (and pairs well
  with the existing large-text and spacing controls).
- Minimal machinery: one THEMES entry (the table drives the swatches and
  the boot restore automatically) plus two "is dark" checks unified.

### Candidates rejected (this cycle)
- **Rename a profile** — organisational; would rewrite every tree in the
  profile; wait for demand.
- **CLI note/highlight commands** — still the minority surface.

---

## Feature 14 — ★ Highlights hub

### What it is
A **★ highlights · n** button in the words tab (and a ⌘K entry) opens a
modal listing **every passage you highlighted across the active profile's
trees**, grouped by tree (most recently touched first), each shown in its
highlighter band with the node and turn it lives in. Tap a passage and
you're standing at the mark in its conversation. Orphaned highlights
(their node was pruned) are skipped, matching what the conversation
renders; the button hides when there's nothing marked.

### Why this one
- The last unserved leg of the highlights feature-family: Feature 5 made
  marks, Feature 8 made them searchable (when you know the words), Feature
  9 archived them in exports. Rereading your marks *without* a query — the
  "flip through your underlines" revision pass — needed an aggregated view.
  Deferred three cycles as lower-priority; with the rest of the study loop
  saturated it's now the best value on the board.
- Pure read-only aggregation over existing data, cloned from the progress
  modal's skeleton (overlay, Esc chain, Tab trap, print hide, focus
  restore), navigating through the existing `openSearchHit` path.

### Candidates rejected (this cycle)
- **High-contrast theme** — real accessibility value; the five themes were
  contrast-validated, but a dedicated black/white/yellow theme is a fair
  future cycle.
- **CLI parity commands (note/highlights in the terminal)** — the CLI is
  the minority surface; web-first still pays better.

---

## Feature 13 — The due count follows you: tab title + app badge

### What it is
When flashcards are waiting, the browser tab reads **(n) topic — learn with
claude** — the pattern every mail client trained us on — and, where the
Badging API exists (installed PWA on Chromium/Edge/Android, plus macOS/iOS
Safari PWAs), the app icon carries the same count. Both clear the moment
the deck is empty, both are scoped to the active profile exactly like the
review deck, and both refresh where the due count already refreshed: every
render, on waking the tab (midnight rollovers), and after review sessions.

### Why this one
- Spaced repetition only works if you come back, and the app's review nudges
  were all *inside* the app (words-tab badge, review button). The tab title
  is visible from every other tab with zero new permissions — the cheapest
  possible retention surface — and the icon badge covers the installed-PWA
  case. All the data already flowed through one function (`updateRevRow`);
  the title just had two writers to reconcile (`renderHeader`).
- Tiny and additive: a shared `applyTitle()` and a guarded
  `setAppBadge`/`clearAppBadge` pair.

### Candidates rejected (this cycle)
- **Cross-tree highlights hub** — still parked; retrieval and archival are
  both served now.
- **Quiz over a whole profile** — model-call heavy, value unclear next to
  per-tree quizzes plus cross-tree review.

---

## Feature 12 — Survey: "know it"

### What it is
Every uncovered piece in the 🗺 survey map gets a **know it** action beside
*investigate*: mark a foundation you already understand and it counts as
covered — shown with the same done styling and a **✓ known** chip (tap to
unmark) — without spending a conversation on it. The progress line becomes
"n/total covered" (investigated or known). The flag lives on the survey item
(`item.known`), so it syncs, exports, and round-trips with the tree like the
rest of the map.

### Why this one
- The survey flow assumes you start from zero, but its own learner picker
  admits you often don't (practitioner, expert-from-a-neighbouring-field).
  For anyone with partial background, half the mapped foundations are
  already known — and the coverage tracker stays misleadingly red unless
  you pay ~$0.05–0.07/turn to "investigate" things you could teach.
  Marking them known makes the map honest and leaves the investigate
  buttons pointing at the actual frontier.
- Small and safe: one optional boolean on survey items, carried by the
  existing survey last-write-wins sync rule and (since Feature 9) the file
  round-trip; two small UI branches in `renderSurvey`.

### Candidates rejected (this cycle)
- **Due-count in tab title + PWA icon badge** — real retention nudge, but
  smaller than making survey coverage truthful; next in line.
- **Cross-tree highlights hub** — still parked.

---

## Feature 11 — (correction) drag-and-drop import already existed; polish it, then: resume where you stopped reading

### The miss, on the record
This cycle initially chose "drop a file to import it" — and mid-implementation
discovered the app **already had it** (a `body.dragging::after` veil and a
document-level drop handler), unmentioned in the README or help. The
duplicate implementation was reverted. What shipped instead:

1. **Polish of the existing drop handler** (a fix, not a feature): it now
   reacts only to drags that actually carry files — previously *any* drag
   (a text selection, say) summoned the "drop a .know.json" veil and
   preventDefault'ed native text-drag behaviour — and a multi-file drop
   imports every file instead of silently taking the first. `dragend` also
   clears the veil if the drag is cancelled.
2. **Documentation**: the README, the in-app hint, and the help panel now
   mention dropping a file — the feature was invisible.

### The actual Feature 11 — resume where you stopped reading
The app already reopens your last tree on boot, but your **scroll position**
lived only in memory: every reload (and every mobile tab eviction — the
common case for a PWA) dumped you back at the top of a long conversation.
Now the per-node reading positions persist (`lwc.scroll.v1`), the boot path
restores the position of the reopened node, and positions for deleted trees
are pruned. A reading tool should open where you left the bookmark.

### Candidates rejected (this cycle)
- **PWA icon badge with due-card count** — only for installed PWAs.
- **Cross-tree highlights hub** — still parked.

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
