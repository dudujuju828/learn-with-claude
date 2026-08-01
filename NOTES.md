# Autonomous feature log

An ongoing log of features added autonomously, newest first. Each entry records
what was chosen, why, and which candidates were rejected.

---

## Feature 55 — ⚡ fact me out: the breadth mode

*(user-requested, after being asked what the learning loop was missing: "a
'fact-me-out' mode (where new, full, survey etc. are) — it just takes a topic
and gives a tonne of 1-sentence facts about the topic (use a good model for
this maybe opus5?)".)*

Every other entry point ends in a conversation — `new`, `full`, `survey`,
`gaps` all produce the learner↔tutor loop, which is the right shape for
understanding one thing and the wrong shape for finding out what is *there*.
`facts` takes a topic and returns the landscape in one call: 6-8 named groups
holding 40-60 one-sentence facts, scannable in two minutes.

**The prompt is the feature**, and two rules do most of the work.

*Specificity.* "Hash tables are widely used" is noise; "a lookup stays O(1)
only while the load factor stays low" is a fact. The system prompt names the
failure ("that is not a fact, it is a noise") rather than gesturing at
quality.

*Never invent precision.* A confidently wrong number under a heading that
says **facts** is the textual version of a confidently wrong diagram — the
reader cannot tell it from the real ones and will repeat it. So: give the
qualitative fact you're sure of ("orders of magnitude slower") over a
specific multiple you're guessing at. Same principle as Feature 54's "omit
rather than invent", which is becoming the house rule for generated content.

**The mix turned out to matter as much as the facts.** The first live run
came back 17-of-48 plain definitions and exactly one number — technically
correct and basically a glossary, which the reader can get anywhere. Adding
an explicit budget (definitions ≤ a third; weight toward mechanism,
consequence, edge, misconception; include real numbers) moved it to 13
definitions and 3 numbers, then to 7-of-36 on a second topic. Misconceptions
are called out as the most valuable kind, because they change something the
reader already believes rather than adding to a pile.

That emphasis immediately caused its own regression — the model started
writing literal `"Misconception: … Correction: …"` prefixes, duplicating the
badge the UI already draws — so the prompt now forbids the prefix explicitly.
Worth recording as a pattern: pushing hard on a quality axis in a prompt
tends to produce a *literal* reading of the push, and needs a matching "don't
say it, just do it" clause.

**It is a menu, not a destination.** Each fact carries ▶ investigate (a real
conversation in that tree, rooting it or chaining as a follow-up exactly like
the survey's) and ❓ bank (to the *global* bank — a fact is about the topic,
not about a passage in something you were reading). The panel tracks which
facts you chased, so it doubles as a record.

`role: "facts"` → `claude-opus-5` hosted (`LEARN_FACTS_MODEL`), the tutor's
model locally, and no tools in either. The role exists because this is
bounded by what the model *knows*, not how well it reasons — and because the
reader treats the output as reference, so recall accuracy is what the strong
model buys. For the same reason it runs at `effort="medium"`: selection, not
deduction, and full effort would only lengthen a call that already emits
~3000 tokens.

**Rejected:** dedupe on `SAME_QUESTION_OVERLAP` (0.7). A fact is a whole
sentence of 12-20 content words, where that bar leaves obvious rewordings in
— two of the harness fixtures sat at 0.67 and were plainly the same fact. It
gets `SAME_FACT_OVERLAP` (0.6) of its own, with the question bar left alone,
since 0.7 is there for a documented reason ("what is a B-tree?" vs "what is a
B-tree node?"). Also rejected: a substring filter box. At 50 facts a filter
is essential, but this app promises forgiven spelling everywhere else, and a
filter that punishes typos would be a strange thing to ship *here* — it
reuses `fuzzyFind`, so word order is free and one typo still lands.

Verified: 47 Python tests (grouping, dedupe, clamping, the total cap, both
exports) and a 25-check headless harness (panel, grouping, badges, filter
including a typo and reversed word order, both exits, the header counter, the
merge). Live on three topics — DNS, linkers, and one deliberately awkward —
which is where the mix problem and the prefix regression were both caught.

---

## Feature 54 — 🖼 illustrate: a picture of the sentence you point at

*(user-requested: "when reading it's nice to sometimes get a visual idea, an
image to pin something down. We don't want this to be automatically
generated, because there is a large chance that the image would be
irrelevant. Therefore — you highlight roughly what you want an image of, and
click a generate image button… Be very careful with the image generation
prompt, images are known to be tricky with AI.")*

Select a descriptive passage in an answer; the selection chip's **🖼 image**
draws a figure and files it under that turn. Nothing is ever illustrated
automatically — the same rule the glossary has (`➕ add` and nothing else),
for the same reason: an unrequested picture is decoration at best, and at
worst a confident picture of the wrong thing, which costs a reader more than
no picture.

**Two stages, because one stage does not work.** The obvious build — send the
selected prose to the image model — is the one that produces the handsome,
irrelevant diagram with invented labels the user was worried about. Image
models draw the *vibe* of a paragraph. So a text model reads the passage
first (`ILLUSTRATE_SYSTEM`) and answers a narrower question: what here has a
**shape**, and what would drawing it teach? Its output is a brief — subject,
kind, layout, elements, and an explicit **label whitelist** — which
`gemini_images.build_prompt()` turns into the image prompt.

Three things fell out of that split which justify it on their own:

- **It can decline.** `{"drawable": false}` is a first-class answer, returned
  as a 200 with a plain reason ("this is an opinion, not a structure") and no
  image bill. Refusing to illustrate an idea with no shape is the difference
  between a feature readers trust and one they learn to scroll past.
- **Alt text exists.** A picture with no alt text would be a step backwards
  for this app specifically. The brief produces it, so a screen reader, the
  markdown export, and a figure whose bytes are missing all still carry
  meaning.
- **"Ask about this image" needs no vision model.** The brief *is* a faithful
  description of the picture, because the picture was drawn from it — so
  🔍 explain and 💬 ask ride the existing `askThunk` path with the brief as
  the quote. Works identically on both backends; no core prompt changed.

**The prompt rules that matter** (each is a specific failure mode): an
explicit, deduped, ≤6-item label whitelist spelled out verbatim — unrequested
text is the commonest way a generated diagram becomes worse than nothing,
since gibberish labels look authoritative; "flat vector textbook figure",
which is the one phrase that reliably keeps the model off photoreal 3-D
renders that impress and explain nothing; a decisive layout, because an
unarranged process diagram is a wrong one; and "leave it out rather than
inventing a plausible-looking stand-in".

**Where the bytes live — the constraint that shaped everything.**
`api/trees.js` caps a tree at 2 MB and the browser keeps *every* tree in one
localStorage key, so a single PNG would crowd out the conversations it was
meant to explain. Rejected: inlining base64 on the turn (≈15 figures per tree,
≈40 per browser, and a `.know.json` no one could read); Vercel Blob (a second
store to provision, and the repo had deliberately migrated off it). Chosen: an
`images` table (bytea) hosted, `knowledge/images/` locally, and the browser
re-encodes to WebP ≤1280px before upload — the Python package stays
stdlib-only because the *canvas* does the work. Measured on a real generated
figure rather than estimated: **390 KB JPEG in, 31 KB WebP out** (12×, 95 ms,
label text still crisp — flat vector art compresses far better than the
~150 KB this entry originally guessed). localStorage after a figure: 1454
bytes.

The tree carries only the description (`images: [{id, node, turn, anchor,
caption, alt, …}]`) — which is what lets a CLI reader, the markdown export,
and an imported tree from another deployment all still say what the figure
was. `export html` is the exception: it is mailed around and read offline, so
the client inlines the bytes as data URIs and the page stays self-contained.
Markdown deliberately does **not** — several hundred KB of base64 per figure
would make the export unreadable in the editors people open `.md` files in.

All four tree invariants honoured: `mergeTrees` unions figures by id with
`imgGone` tombstones (without them a deleted figure returns from another
device as a permanently broken box, since its bytes are gone); `extras`
carries `images` through the CLI; both exports handle it; and figures are
per-tree so they inherit the tree's profile.

One transport oddity worth recording: `/api/images` is the sole `/api/*` path
the service worker caches. An id is minted per figure and never reused — a
redraw mints a new one — so the bytes behind a URL can never change, which
makes cache-first correct rather than merely convenient, and means figures
survive an offline read.

**Rejected:** a confirmation step showing the brief before drawing (the user
asked for select → click → image; the fix path is `↻ redraw`, which takes an
optional steer or just tries again, since these models are stochastic);
passing the image to Claude's vision (hosted-only, and it would fork
`call_model`'s contract, which local mode could not follow); a figures
gallery (nothing asked for it, and every new cross-tree view is another place
to get profile scoping wrong).

Verified with the repo's headless-Edge stub harness — 38 checks, from "the
chip offers the button" through re-encode, upload, tombstoned redraw, the
merge, and a refusal not reading as an error.

Then verified live, which is the only way to judge the part that actually
matters. Three real tutor passages through the whole two-stage route:

- *chaining* → the art director picked `structure`/4:3 and the labels
  `Bucket, Linked list, Key 1, Key 2`; the figure is a bucket column with the
  third bucket pointing at a two-node list with next-pointer cells.
- *the TCP handshake* → `process`/16:9, labels `Client, Server, SYN,
  SYN-ACK, ACK`; a correct sequence diagram, three arrows, right order,
  right directions.
- *"naming things well is mostly a matter of taste"* → **declined**, with
  "no physical form or spatial layout". The refusal path is not theoretical.

**No hallucinated text in any of them** — the label whitelist is doing the job
it was written for, which was the whole risk in this feature.

Two defects the live run caught. Gemini returns **JPEG**, not the PNG the
docs' examples imply (harmless — every layer takes the mime as given — but
the harness had only ever fed it a PNG). And a project without billing is
refused as a **429**, which was being reported as "wait a moment and try
again": an instruction to loop forever on a wall that never moves. It now
reads the `limit: 0`/`free_tier` marker and says to enable billing instead.

---

## Feature 53 — profiles become real records, owned by the server

*(user-requested: "consistently getting an issue with the lifecycle of
profiles (creating one means it's not there — it seems to want to also
automatically include the last conversation to a profile) — audit the full
pipeline for bugs — where you can, make the server the authority".)*

**The root cause was that a profile had no existence of its own.**
`allProfiles()` derived the list from the `tree.profile` strings it found in
the store, so a profile existed only while some tree wore its name. Every
reported symptom falls out of that one fact:

- the only way to create a profile was `fileTreeUnder("__new")`, which
  prompts for a name and immediately assigns it to the **open** tree — so
  "new profile" literally meant "refile the conversation I'm looking at";
- `fileTreeUnder` only moved the active selection when a profile was
  *already* active (`if (wasActive && …)`), so creating one from **all
  trees** left you on "all" with a chip you hadn't selected — "creating one
  means it's not there";
- `activeProfile()` re-validated against `allProfiles()` on every call, so
  refiling or deleting the last tree in a profile silently returned "" and
  threw you back to "all trees" — the name gone for good, and any global
  question still filed under it now invisible in every view;
- because `newTree()` reads `activeProfile()`, that evaporation also meant
  new conversations were born profile-less, so the profile could not come
  back by using it;
- `prefs.profile` was a device preference in `localStorage`, and the set of
  profiles was computed from whatever the local cache happened to hold — on
  a fresh device the chip row was empty until the first sync finished.

**Chosen: keep the filing on the tree, add a registry beside it.** A profile
is now two halves. The *filing* stays a name on the tree doc, because that is
what makes it sync, merge, and travel in `.know.json` to the CLI and back.
The *registry* is a new synced document, `settings:profiles` (`api/profiles.js`
hosted, `ProfileStore` → `profiles.json` locally), holding one record per
profile. `allProfiles()` is the **union** of the two, which is the important
detail: a registered profile survives with zero trees, and a tree arriving
from the CLI wearing an unknown name still shows up rather than pointing at
nothing. `adoptTreeProfiles()` turns such a name into a real record on sync,
import, and drop.

`active` lives in that same document, so the server is the authority on which
profile you are in and every device agrees instead of drifting — the local
copy is only a cache that makes the first paint instant. The registry also
carries the per-profile tutor style, learner level, and thinking-blocks
toggle (`PROFILE_SETTINGS`), so *history* keeps its plain-words tutor while
*computer-science* keeps its technical one; `prefs` still holds the live
values, so every existing reader of `prefs.tmode` is untouched.

Creating a profile is now its own action (the dashed **＋** chip, always
present so the first one is reachable): it registers the name, selects it,
and **clears the open conversation** so the new interest starts genuinely
empty. ✕ deletes a profile and moves its trees, questions, and tutors back
to *no profile* — the conversations are the expensive artifact and must
never disappear with a chip.

Encapsulation was extended to the two things still leaking: custom tutors
gained an optional `profile` (filed = offered only there, unfiled = offered
everywhere, with a checkbox in the editor), and `save all` now backs up the
profile you're in — carrying the registry entries, or an empty profile would
not survive the round trip — and still backs up everything on "all".

**Rejected:**

- *keying trees by a profile **id** rather than a name.* Rename-safe, but it
  breaks portability: `.know.json` would carry an opaque id the CLI can't
  resolve, and an imported tree would need a mapping table. Renaming already
  restamps every tree, which is cheap and keeps the file human-readable.
- *tombstoning deleted profiles.* The union means a straggling offline tree
  can resurrect a name. That is the better failure — a resurrected chip is
  visible and deletable, an orphaned tree filed under a profile nothing
  lists is not.
- *leaving `active` in device prefs.* It is the one thing that makes the
  lifecycle deterministic across devices, and it was explicitly asked for.
- *deleting a profile's conversations with it.* Never.

Verified with the usual stub-harness-plus-headless-Edge pattern: 44 checks
over the full lifecycle (create → inherit → switch → per-profile settings →
survive the last tree → rename → delete → adopt → tutor scoping → server
wins → cache), plus a migration probe run against **both** `HEAD` and the
working tree, which reproduces the swallowed-conversation and evaporation
bugs on the old build and passes on the new one.

---

## Feature 52 — ↗ promote a question from the local bank to the global one

*(user-requested: "implement the ability to promote a question from the
local-bank to the global-bank".)*

### What it is
A third action on every pending row of a tree's ❓ question bank. It moves the
question to the global bank, and the local bank folds it away under
**↗ moved to the global bank** with a jump across to where it went.

### Design notes
- **It's a change of answer, not of filing.** The two banks answer a question
  completely differently — the local one sends it straight to this tutor with
  this conversation's context and files the reply as your turn in this tree;
  the global one starts a brand-new investigation with the question as its
  topic. So promoting is the move for a question that turns out not to be
  about the passage you jotted it against, but a topic in its own right. The
  button's tooltip says exactly that, since "promote" alone doesn't.
- **A move, and the move is a one-way flag rather than a splice.** This is the
  whole subtlety. `mergeTrees()` unions `questions` by id starting from the
  *server's* copy, so a spliced-out question comes back on the next 409 merge —
  and it would come back alongside the global copy, leaving the question in
  both banks at once, which is the one outcome a move must never produce.
  `promoted` flips one way exactly like `answered` already does, and rides the
  same merge rule. Rejected: splicing (matches the existing `discard`, and is
  wrong here for that reason); a `gone`-style tombstone array (the glossary's
  pattern, but overkill when the record itself can just carry a flag, and the
  flag doubles as the on-screen trace).
- **It carries the TREE's profile, not the active one.** `addGlobalQuestion()`
  filed under `activeProfile()`, which is "" whenever no profile is selected —
  a question promoted then would have shown up in every profile. It now takes
  an optional explicit profile, and the duplicate check (`bankedUnder`) is
  profile-aware to match, since `isBanked()` asks about the profile you're *in*
  rather than the one being filed under.
- **Already in the global bank under that profile?** Then it still leaves the
  local bank, it just doesn't duplicate. The move is the point; the copy is
  incidental.
- **A queued investigate can't fire on a promoted question.** Press *run all*,
  then promote one before the queue reaches it: `bankInvestigateThunk` now
  checks `promoted` alongside `answered`, so the old tree doesn't answer a
  question that has left it.
- Verified with 33 browser assertions, including both merge directions, the
  run-all race, the profile-aware duplicate check, and that promoting twice or
  promoting an answered question is a no-op.

---

## Feature 51 — 📄 exam: a written paper on the open conversation

*(user-requested: "an open-ended university style-question page that asks essay
like questions… configurable with question count (default-5)… Marking will be
done by a smart model - feedback will be ~2 paragraphs / question - with
10marks/question… It should award use of technical terms - along with
conceptual ideas".)*

### What it is
**📄 exam** in the conversation header, beside quiz and explain. Pick a
question count (3–8, default 5), and the examiner sets an essay paper on that
conversation: one textbox per question, one submit at the end. Each is out of
10. Marking comes back as two paragraphs per question — what your answer
earned, and what a full-mark answer would have said — plus a total, the scheme
points you hit and missed, and one comment on the script as a whole.

### Design notes
- **The paper is set from the conversation but never quotes it.** This is the
  whole point of the feature existing next to `🎓 quiz`. Multiple choice can be
  passed on recognition, and recognition is exactly the false signal
  `_LEARNER_CORE` already warns about ("a tidy answer you have just read is NOT
  an answer you hold"). So `EXAM_SYSTEM` gets the transcript framed as the
  *syllabus* — the boundary of what may be examined — with an explicit ban on
  quoting it, referring to it, or asking for a definition it stated.
- **Six question archetypes, chosen for what they extract**, not for variety's
  sake: mechanism (a causal chain is where half-understanding snaps),
  discriminate (understanding lives at concept boundaries), transfer (a case
  the tutorial never mentioned — recall simply cannot answer it, which makes it
  the strongest evidence a model is held), counterfactual (a real model
  predicts; a remembered one goes quiet), claim-to-assess (aimed at the
  misconception the transcript shows the learner actually having), and
  judgement under constraint. Any paper of 4+ must contain a transfer and a
  claim. Ordered by ascending demand, so someone about to fall over gets to
  stand up first.
- **The mark scheme is written WITH each question, and published to the
  marker.** This is the single biggest lever on whether the feedback is sound:
  marking essays "from vibes" drifts between sittings, and a question nobody
  can write a scheme for is a vague question. Each question carries 3–5
  `points` (specific claims a full-mark answer establishes) and 2–6 `terms`.
  Rejected: marking straight from the transcript with no scheme — much cheaper
  to build, and it makes two sittings of the same paper incomparable.
- **Marks split 7 content / 3 precision**, which is how "award technical terms
  *along with* conceptual ideas" stays fair in both directions. Terms earn for
  correct *use*, never for appearing; and an answer that is conceptually right
  in everyday words keeps all its content marks and can still reach 7. Nobody
  is marked down for not reaching for a word.
- **One marking call for the whole script**, not one per question: an examiner
  marks a script. It is what makes the overall comment worth anything, and it
  lets the marker notice the same confusion surfacing twice instead of scoring
  it as two unrelated failures.
- **Arithmetic is ours, not the model's.** `handle_mark_exam` clamps every mark
  to 0–10 and sums the total itself, so the number on screen is right even when
  the prose around it is generous. A missing or garbage result scores 0 rather
  than throwing the whole script away.
- **Two paragraphs, as two fields.** `earned` / `improve` rather than one
  `feedback` string the model can quietly collapse into one paragraph — and it
  lets each render in its own labelled card, reusing the explain-it-back
  pattern. A blank answer gets 0, and `improve` becomes a compact model answer,
  so an unanswered question still teaches something.
- **Scoped to the open conversation, not the tree.** A tree spans several
  investigations; an exam roaming across all of them would test breadth, which
  the quiz already does. Profile scoping comes free (papers live on the tree),
  and both aggregate views — 📊 progress and 📅 today — walk `profileTrees()`.
- **Full transcript, not `conversationDigest()`.** The digest clips every tutor
  answer to 240 characters. Fine for reminding a learner what was covered,
  useless as a syllabus: it produces questions the material never supported,
  and marks a correct answer wrong because the marker never saw the sentence
  that licensed it.
- **A new `examiner` role**, so the two hardest judgement calls in the app can
  point at a stronger model — hosted defaults to `claude-opus-5`
  (`LEARN_EXAMINER_MODEL` dials it back); locally it rides the tutor's model
  rather than adding a fourth dropdown nobody would set differently. A soft
  mark reads exactly like a good one, which is why this is the place to spend.
- **Answers autosave as you type** (debounced, plus blur/close/hide/unload).
  An essay half-written and lost to a phone evicting the tab would be the worst
  bug this feature could have. The merge rule follows from that: union by id, a
  *submitted* paper always beats an unsubmitted copy of itself, and between two
  drafts the later `saved` stamp wins.
- **❓ bank it on every question**, in both the answering and the marked view —
  an exam question you can't answer is the purest "something I don't know" this
  app produces. It goes to the global bank (profile-scoped like everything
  there) and the sitting carries on, rather than being abandoned to go look it
  up.
- Submitting with blanks asks once, then submits. Leaving a question blank is a
  legitimate move; doing it by mis-click on a paper you meant to finish is not.
- Verified with 55 browser assertions over the whole flow (setup → paper →
  autosave → banking → confirm-on-blank → marking → badge → reopen), including
  cross-profile isolation with a real second profile, pruned-node handling, and
  all four merge cases; plus 3 new Python tests over the two handlers and the
  export path.

---

## Feature 50 — 💬 ask a question about the passage you selected

*(user-requested: "the ability to highlight then send a question which
references the text that you highlighted, so that the tutor can respond in the
context of what you are learning".)*

### What it is
Select any sentence in an answer, press **💬 ask**, and a bar opens with that
passage quoted above it. Type your question; it goes to the tutor with the
passage attached, so the answer is about *that claim* rather than the topic in
general.

### Design notes
- **It fills a real gap between two things that already existed.** `⛏ dig`
  asks a *fixed* question about a selection; "ask the tutor yourself" asks
  *your* question but anchored to nothing narrower than the node. Neither lets
  you ask your own question about a specific sentence, which is what you
  actually want mid-read.
- **The quote is its own field, not glued into the question.** `rec.quote`
  holds the passage; `rec.action` stays the question you literally typed.
  Only the model sees them combined (`askedWithQuote`, in a `<<< >>>` block).
  That keeps the transcript, the digests that seed branches, search, and the
  exports all working with a clean question, and lets the passage render as a
  quotation above it rather than as noise inside it.
- **It reuses the ❓ capture bar rather than adding a dialog.** That bar exists
  precisely to take a question without dimming the page or losing your scroll
  position — exactly right here too. It gained a third mode (`ask`) alongside
  global and local banking; `saveQCap` branches once at the top, since ask
  doesn't bank anything, it sends.
- **Turn fields survive the CLI round trip already** (`Node(**…)` filters
  node-level keys; turns pass through as raw dicts), so `quote` travels in
  `.know.json` with no Python change beyond rendering it — a `> ❝ About: …`
  line in the markdown export and a quoted block in the HTML one.
- Verified with a real Copilot call: quoting *"Lookup is average O(1) because
  the slot is computed, not searched"* and asking *"so when does that stop
  being true?"* got collisions, load factor, and degradation to O(n) — the
  answer to that claim, not a re-definition of hash tables. Plus 19 browser
  assertions over the whole flow, and a check that the chip's seventh button
  still wraps to fit a 390px phone (666px natural, 58px in two rows).

---

## Feature 49 — profiles actually contain everything

*(user-requested: "ensure that profiles fully encapsulate all aspects of the
application (glossary, qbank, etc.)".)*

### What it is
The active profile now scopes every surface, not just the tree list and the
review deck. An audit of every walk over `store` turned up four leaks, plus
one whole feature with no notion of profiles at all.

### The leaks
- **Search** — all four passes (turn text, glossary, highlights, notes) walked
  the entire store, so searching inside *computer-science* surfaced hits from
  *biology*.
- **The glossary's "all trees" scope** — meant *literally* all trees. It now
  means all trees in this profile, which is what that toggle sitting next to a
  profile chip plainly implies.
- **The ⌘K palette** — listed and jumped to trees the tree list wouldn't show.
- **"Open the latest tree"** on boot and after a sync — could drop you into a
  tree from a profile you weren't in, which then wasn't in the list beside it.
- **The global question bank had no profile at all.** Questions now carry one,
  taken from the active profile when banked.

### Design notes
- **The document keeps every question; only the views filter.** That matters
  for ⇅ order, which rewrites `globalQDoc.questions` wholesale — filtering
  there would have *deleted* every other profile's questions. It rebuilds from
  `otherProfileQuestions()` plus the visible ones, and there's a test that
  would have caught exactly that mistake.
- **Legacy data behaves like legacy trees.** A question banked before this
  (no `profile`) is hidden while a profile is active and visible when none is
  — the same rule `inProfile()` has always applied to unfiled trees, so the
  two are consistent rather than each surprising in a different way.
- **Renaming a profile carries its questions**, not just its trees.
- **What stays global on purpose:** the full `save all` backup (a backup that
  quietly omitted other profiles would be a trap), `allProfiles()`, and custom
  tutors — a tutor style is a preference about how you like to be taught, not
  knowledge filed under an interest.
- 26 browser assertions across two profiles with distinctly-named data in
  every surface: isolation, that switching flips all of it, that no profile
  still shows everything, and that a rename moves trees and questions
  together. All five earlier suites re-run green — 164 assertions in total.

---

## Feature 48 — notes get markup, and actually save

*(user-requested: "improve the notes — give it basic markup (headers, bullet
points, fonts, bold, underline, etc.) and ensure they are saved to the
server".)*

### What it is
The notes editor gains a toolbar over a small markdown subset — headings,
bullet and numbered lists, quotes, rules, bold/italic/underline/code, with
Ctrl+B/I/U/H — plus a **👁 preview**. And it now autosaves.

### Design notes
- **Markdown, not rich text, because the note is already markdown
  everywhere it goes.** `knowledge.to_markdown()` drops it under
  `## My notes` and the study sheet compiles it the same way; storing HTML
  would have broken both exports and the CLI. Writing markdown makes those
  outputs *more* correct, not less. Underline is the one thing markdown
  lacks, so `<u>` passes through — valid markdown, renders everywhere.
- **Per-note font pickers were the one part of the request I left out.** The
  app already has a global, dyslexia-driven font switcher; a per-note
  override would fight it, and it can't survive a markdown round trip. Bold /
  italic / underline / code cover what the toolbar is actually for.
- **The autosave was a real bug, and the README was already claiming it.**
  Notes persisted *only* in `closeNotes()`. Close the tab — or let a phone
  evict it — with the editor open and everything typed was gone. Now every
  keystroke schedules a save 600ms out, and blur, `visibilitychange`,
  `pagehide`, and closing the box all flush immediately. From there the
  existing machinery takes over: `persistTree` marks the tree dirty,
  `flushDirty` pushes it, and the `beforeunload` handler already beacons
  anything unsynced on the way out. A "✓ saved" line makes it visible.
- **Then it became a live editor**, because a preview toggle isn't what
  "renders as you type" means. The textarea is gone: notes are now a
  contenteditable holding one `<div>` per source line, restyled on every
  keystroke. Markers stay on screen **dimmed** rather than disappearing —
  Bear/iA Writer's approach, not Notion's — which buys two things that matter
  more than the last 5% of polish: the on-screen character count always
  matches the source exactly (so caret arithmetic is trivial and honest), and
  nothing reflows out from under the cursor when the caret leaves a line.
- **The parts a hand-rolled contenteditable actually has to solve**, all
  covered: caret restored by character offset after each re-render; a render
  skipped entirely when the HTML wouldn't change; paste forced to plain text
  (otherwise styled HTML walks in from anywhere); and our own undo stack,
  since rewriting `innerHTML` destroys the native one. The undo has one
  non-obvious rule — the debounced snapshot records the state *at rest*, so
  the top of the stack is usually where you already are and the step has to
  skip past it. A test caught that.
- **Rendering is duplicated deliberately.** `note_md()` (Python, for the HTML
  export) and the editor's own line renderer
  (Python, for the HTML export) implement the same subset with the same
  escape-first discipline — escape everything, then build only the tags the
  renderer itself creates, so no note can inject markup. `<img src=x
  onerror=…>` comes out as text; there's a test for it on both sides.
- The toolbar toggles: pressing • on lines that are already bullets takes the
  bullets off, and numbered lists renumber from 1.
- 25 browser assertions (renderer, every toolbar button, preview, and each
  autosave trigger including a simulated tab-hide and pagehide), 8 layout
  measurements, and Python coverage of the export renderer.

---

## Feature 47 — ❓ bank it, from an explain-it-back probe

*(user-requested: "when doing an explain-it-back it may end up asking a
question that you don't know the answer to, in which case there should be an
option to add it to your global question-bank".)*

### What it is
A second button beside **⤳ chase it** on the tutor's probing question. Chase
spends a model call and closes the box; **❓ bank it** files the question in
the global bank and leaves the thread exactly where it was.

### Design notes
- **The point is that it doesn't interrupt.** Chasing was the only existing
  answer to "I don't know this", and it ends the explain-back to go answer it
  elsewhere. Banking is the opposite move: park it, keep explaining, come back
  to it whenever. So this deliberately does *not* close the box, costs no
  model call, and re-renders in place.
- **Global, not the tree's own bank** — as asked, and it's the right home: the
  probe surfaces something *you* don't know, which is what the global bank is
  for, rather than a note about this particular conversation.
- **It reads ✓ banked once it's in**, computed from the bank itself
  (`isBanked`, normalised for case and punctuation) rather than from a stored
  flag — so it survives a re-render, revisiting an old attempt from the trail,
  and a sync from another device, with nothing new persisted anywhere.
- 15 browser assertions over the real flow: the question reaches the global
  bank verbatim, the box stays open with its thread intact, the button flips,
  it can't be filed twice, and it turns up investigable in the bank UI.

---

## Feature 46 — ✨ suggest questions (global bank)

*(user-requested: "a 'suggest questions' feature that looks at the current
questions and suggests a few questions to be added or not — the user
ultimately decides whether or not to keep it". Global bank only, per the
follow-up.)*

### What it is
A button in the global bank: it reads what you've banked and proposes up to
four questions it implies but you never wrote down — the prerequisite
underneath them, the obvious next step, the case they all quietly assume.
They arrive in a dashed, visibly-provisional panel with **+** and **✕** per
suggestion, plus add-all and dismiss-all.

### Design notes
- **Nothing is added by the call.** The route returns text and the UI holds it
  in a module-level array — no tree field, no synced doc, no export, no merge
  rule. A suggestion becomes real only when `takeSuggestion()` runs
  `addGlobalQuestion()` on it. That kept the whole feature to one route and
  one render block, and it's why "dismissed suggestions never touch the synced
  doc" is trivially true rather than something to police.
- **Session-only was the right call for provisional data.** Persisting them
  would mean a new synced field for things the reader hasn't agreed to keep;
  losing them on reload costs one cheap call.
- **Duplicate rejection needed to be fuzzy, and the test caught that.** An
  exact normalised-key match let "Why is the fanout of B-trees high?" through
  against a banked "why do B-trees have high fanout?" — one filler word apart.
  It now compares content-word sets by Jaccard overlap at 0.7, which catches
  the re-wording while leaving "what is a B-tree?" and "what is a B-tree
  node?" (0.67) as the genuinely different questions they are. Suggestions are
  also deduped against each other within a batch.
- **Global only, as asked.** The local bank already has a tree behind it —
  `→ next`, `🔬 look deeper` and the survey map all propose what to cover
  next there. The global bank had nothing of the kind, and its banked
  questions are the only context it has.
- Real call on three B-tree/postgres questions returned MVCC and index
  visibility, page size versus fanout, and planner statistics — three things
  the bank plainly implied and none of them a restatement. 19 browser
  assertions cover keep, reject, add-all, dismiss-all, the already-banked
  filter, and that nothing leaks into the doc.

---

## Feature 45 — ⇅ order the question bank by dependency

*(user-requested: "the AI will organize the questions in dependency order
(both global bank and local) — if there are two questions on a related
concept, which question is best to understand first? (make it a button you
press to organize)".)*

### What it is
A button in both question banks, shown once two questions are waiting. One
cheap model call sorts the pending list into the order it's best learned in:
where two questions touch the same idea, whichever the other one needs
answered first goes first; unrelated questions keep roughly where they were.

### Design notes
- **The model returns positions, never the questions.** `handle_order_questions`
  sends the text and gets back `{"order": [indices]}`, then *repairs* the
  result: out-of-range, duplicate, and non-integer entries are dropped, and
  anything the model omitted is appended in its original order. The output is
  always a permutation of the input, so pressing the button can never lose,
  duplicate, or invent a question — worst case (an unusable reply) it returns
  the order you already had. Tested against six malformed replies.
- **The local bank needed a `seq`, the global one didn't.** `mergeTrees`
  unions `tree.questions` by id and keeps the *server's* order, so a reorder
  made on one device would have vanished at the next sync. Pending questions
  now sort by a stamped `seq`, merged by recency the way a hand-edited
  glossary definition already is. The global bank is its own whole-document
  last-write-wins doc, so there the array order simply *is* the order.
- **Shared route, so both deployments get it.** It lives in `webapi.py`'s
  route table, which means the hosted Vercel app has it as much as
  `learn --web` — the one extra step was adding `order_questions` to
  `vercel.json`'s rewrite list, which is easy to miss.
- Runs on the cheap `glossary` role at `effort: none`; the local bank charges
  it to the node so the header stays honest.
- Verified with a real call on five hash-table questions, deliberately jotted
  out of order: it returned hash function → collisions/chaining → open
  addressing → resizing → consistent hashing. Plus 18 browser assertions over
  both banks (reorder, nothing lost, seq stamped, survives a merge against a
  server copy holding the old order, persists across reopen, no button for a
  single question).

---

## Feature 44 — Shift+N opens my notes

*(user-requested.)* Shifted like Shift+Q, and for the same reason: it belongs
to the tree you're reading and needs one open, so plain `n` stays free for
something that works with nothing open. Listed in the help table, on the notes
button's tooltip, and beside the ⌘K palette entry. Browser-tested including
that typing `N` inside the notes textarea doesn't re-fire it.

---

## Removal — Excalidraw diagrams

*(user-requested: "remove the excalidraw feature entirely from the
application (all traces of it)".)*

### What went
The CLI tutor's optional drawing hand: give it an Obsidian vault and the
`excalidraw-skills` MCP server and it could sketch a small flowchart into
the vault alongside its answer.

- `learn_with_claude/diagrams.py` — deleted.
- `personas.TUTOR_DIAGRAM_SYSTEM` — deleted, and `tutor_system()` lost its
  required `diagrams` keyword. The tool clause is now simply `grounding or
  TUTOR_NO_TOOLS`.
- `cli.py` — `--vault` and `--no-diagrams` gone, along with the vault/server
  resolution and its two warnings.
- `repl.py` — the `vault` field and the four call sites that threaded it.
- `simulator.py` — no vault parameter, no MCP config, no allowed-tools list.
- `backend.py` — `ClaudeSession`'s `mcp_config` and `allowed_tools`
  parameters, the temp-file MCP config writer, and the now-unused `tempfile`
  import. **`--strict-mcp-config` stays**: it is what stops the operator's own
  globally registered MCP servers leaking into a persona, and that guarantee
  never depended on diagrams.
- README: the intro paragraph, the whole *Diagrams (optional)* section, both
  option rows, the project-layout line, and the "not in the web app" mention.
  The no-tools guarantee the Diagrams section happened to carry moved into
  *Notes & limitations*, where it stands on its own.

### Notes
- Nothing in the web app referenced it — the hosted and local backends always
  called `tutor_system(diagrams=False, …)`, so the whole removal is CLI-side
  plus one keyword argument.
- Verified with a real learner↔tutor exchange through the Copilot CLI after
  the cut, plus 32 green tests and a repo-wide grep for
  excalidraw/diagram/vault/obsidian.
- The three surviving mentions are in the entries below, which are a dated
  record of what was decided when — including a *rejected* candidate
  ("Mermaid diagrams in web tutor answers"). Rewriting them would falsify the
  log, so they stay as history.

---

## Feature 43 — the tutor can start from a past Copilot session (local mode)

*(user-requested: "when you leave a local copilot session it gives you the
option to resume it with some hash — it would be good if you can set the
teacher's memory starting from that context (keyed by the hash)".)*

### What it is
A field in **⚙ local settings**: paste the session id the Copilot CLI prints
when you leave a session (a unique prefix works, or pick it off a list of
recent sessions shown right there), and whatever you worked through in that
session is already known to the tutor. Ask about your ingest pipeline without
re-explaining it. Tutor only — the learner and glossary personas never see it.

### Design notes
- **`--resume` per call would have been wrong, and it took a real experiment
  to know that.** `copilot -p … --resume <id>` does work non-interactively and
  the model does recall the session. But it **appends**: one trivial
  `-p --resume` call took a session's `events.jsonl` from 17,752 to 35,538
  bytes. Since this app composes the *whole* conversation into every prompt,
  chaining would (a) rewrite the user's own session full of learn-with-claude
  scaffolding, (b) duplicate the conversation once per turn, and (c) stop
  being "starting from that context" after turn one. The transport here is
  one stateless subprocess per call; the honest fit is to read the session
  once and hand it over as memory.
- **So: read `events.jsonl`, don't resume.** `copilot_sessions.py` parses the
  CLI's own session-state directory — `user.message`/`assistant.message`
  events only, using `content` (what was said) rather than
  `transformedContent` (which carries the CLI's injected preamble), skipping
  tool-only turns. The anchor session is opened read-only and is never
  written to; a test asserts it stays byte-identical across a real tutor call.
- **The format is private, so every read is defensive.** Unparseable lines are
  skipped, a missing or deleted session yields no memory rather than an error,
  and `resolve()` only accepts an id-shaped string (so `../../etc` can't be a
  session id).
- **It plugs into the existing grounding seam.** `grounding_text()` was
  already evaluated fresh per request and already flowed into
  `tutor_system(grounding=…)`; the memory is just a second block beside the
  local-tools one. No route changes, no new endpoint. It's cached on the
  session file's (size, mtime) because a long session is hundreds of KB and
  this runs on every tutor turn.
- **The whole session goes over, not an abridgement of it.** The first cut of
  this shipped a 16k-character ceiling (head + tail, middle elided) and a 4k
  per-message truncation. Both were wrong, and the user caught it: anchoring a
  long conversation *because you want to study it*, only for the tutor to be
  handed the first and last slices of it, defeats the entire feature — and the
  per-message cut was worse, chopping individual answers mid-sentence. The
  ceiling also bought less safety than it appeared to: the CLI compacts an
  over-long prompt itself (better than head/tail slicing), the tutor's
  oversized prompts already travel via a temp file it reads with `view`, and a
  session's *conversation* is a small fraction of its `events.jsonl` once tool
  calls, reasoning blobs, and file dumps are stripped. Now: no limit by
  default, `LEARN_SESSION_MEMORY_MAX` for anyone who wants one, and the
  settings panel states the extent outright — "60 messages, 28k chars — all of
  it goes to the tutor", or a ⚠ naming the cap when one bites. Nothing is
  trimmed silently.
- **Re-read vs. re-sent.** The transcript is parsed once and cached on the
  session file's (size, mtime), but it *is* re-sent on every tutor turn — the
  transport is one stateless subprocess per call, so the prompt is the only
  memory there is. That costs no extra billing in local mode (premium
  requests are per call, not per token); it spends context-window headroom.
- **Framed as memory, not as a document.** The prompt tells the tutor this is
  its own record of working with this learner: treat it as established, let it
  set the level, never mention the session or recap it, and never let it
  displace the actual question.
- **You never need to leave the session to anchor it.** Slash commands are
  interactive-only (`copilot -p "/session"` just treats it as a prompt), but
  the CLI flushes `events.jsonl` per turn — watched live, it went 0 → 12,676 →
  20,571 bytes while the process was still running — so a session in progress
  is already in the picker, and because the memory is cached on (size, mtime)
  it *keeps up* as that session grows. Anchor a session you're still working
  in and the tutor tracks it.
- **`/rename` names resolve too.** Each session dir has a `workspace.yaml`
  with `id`, `cwd`, `name`, and `user_named`; `--resume` accepts a name, so
  `resolve()` now does as well (exact, case-insensitive, and only for names a
  human actually set — the auto-generated one is just the first prompt). That
  makes the without-exiting workflow one step: `/rename parser-work` in the
  live session, type `parser-work` here. The *id* is what gets stored, so
  renaming the session later can't break the anchor. The YAML is hand-parsed
  (flat keys plus the odd block scalar) to keep the package stdlib-only.
- **The learner needed its own, thinner version of this — and finding that
  out took using it.** Giving the memory to the tutor alone looked right (the
  learner must stay uncontaminated roleplay) but was wrong in practice: the
  learner *drives every question*, so it met a domain term it had never seen,
  misread it, and aimed the whole investigation somewhere useless. Handing it
  the transcript would fix that and destroy the tool — a naive learner reading
  expert Q&A stops being naive, and its ignorance is the entire engine here.
  So it gets a **generated orientation brief**: two to four sentences on what
  the territory is, then the names in play with a short "what kind of thing"
  tag each — explicitly no mechanisms, no conclusions, no numbers. A map
  legend, not the map. The prompt block around it is framed as *setting*:
  never quote it, recognising a name is not understanding it, never let it
  supply an answer, and it never sets the agenda.
  Measured before/after on the same topic: without the brief the learner spent
  its whole first turn asking what a "manifest" even is ("a static file, a
  runtime data structure, or something else?"); with it, the first question
  was the real one — "what exact fields in a retailer manifest does the
  promise service need to compute a delivery window?" — and it still had to
  ask, never parroting the transcript.
- **The brief is cached by growth, not mtime.** It is generated, not read, so
  a live session would otherwise buy a new one every single turn. A grown
  session earns a fresh brief only once it moves materially (+6k chars or
  +25%) — a domain's vocabulary doesn't change every time somebody asks
  another question. It runs on the cheap `glossary` role, its cost rides back
  with the learner turn that triggered it so the header stays honest, and a
  failed generation keeps the last good brief rather than breaking the run.
- **`model_routes` grew a symmetric `learner_grounding` hook.** The hosted
  backend passes neither hook, so `api/index.py` is byte-for-byte what it was
  — asserted in the tests.
- **The picker hides the app's own calls.** Every model call this app makes is
  itself a Copilot session, and on a machine that has run `learn --web` for a
  while they vastly outnumber the real ones — so sessions whose first message
  opens with `compose_prompt()`'s banner are filtered out of the list.
- Verified three ways: unit tests (parsing, prefix resolution, filtering,
  whole-session fidelity, opt-in capping, tutor-only reach), 25 end-to-end
  checks driving the real server and the real panel over CDP (pick → save →
  persist → reject a bad id → clear), and **real Copilot calls** with a
  session anchored. The decisive one: a 60-message, 27.8k-char session with a
  distinctive fact planted at exchange 15 of 30 — dead in the middle, exactly
  what the old ceiling discarded, and past the argv limit so it travelled via
  the temp file. The tutor recalled it precisely, never mentioned a
  transcript, and left the session byte-identical. 0 premium requests.

### Candidates rejected (this cycle)
- **Chaining `--resume` per call** — see above; measured, not assumed.
- **Copying the session into a temp `COPILOT_HOME` to fork it** — would keep
  the CLI's own resume machinery, but a temp home loses the login, and
  copying an opaque sqlite session store per call is worse than reading a
  transcript.
- **Asking the model to summarise the session once via `--resume`** — a
  supported interface, but it costs a request, is non-deterministic, and
  still writes to the session it was meant to leave alone.
- **Anchoring per tree rather than globally** — arguably better fit (one tree,
  one project), but the anchor is a property of *this machine's* Copilot
  install, and tree documents sync to other devices and travel in
  `.know.json` where a local session id is meaningless.

---

## Feature 42 — ▶ investigate, from a selection

*(user-requested: "on highlight — an investigate button, along with the
other 'on highlight' buttons — that just takes that exact thing you
highlighted and puts it into a new fresh investigation (separate
context)".)*

### What it is
A sixth action on the selection chip. Select a word or a whole sentence in
any answer, press **▶ investigate**, and that exact text becomes the topic
of a brand-new tree — its own root, its own context, nothing carried over
from what you were reading.

### Design notes
- **Zero new machinery.** `rootThunk(topic)` already does exactly this,
  and the global question bank's *investigate* already uses it for the
  same purpose ("a brand-new root investigation with the question's own
  text as the topic, exactly as if you'd typed it into the topic box and
  pressed new"). The handler is four lines: guard, `closeMenu()`,
  `cmdNew(topic)`. No backend change, no new tree field, nothing new to
  merge, sync, or export.
- **"Separate context" is enforced by using the ordinary root path, not
  by stripping anything.** `runInvestigation` only adds a grounding
  `source` when the *tree* has one, and a fresh tree has none; the
  branch/deepen paths are what inject a breadcrumb and digest, and those
  aren't involved. The probe asserts this at the wire: the `/api/learner`
  body is `kind: "root"` with `topic` exactly the selected text, empty
  `turns`, and no `source`/`breadcrumb`/`digest`/`baseline`.
- **It does inherit the three things a new tree always inherits** — the
  active profile (so it files where you're working), the tutor style, and
  the learner level. Those are device/session preferences, not context
  from the tree you were reading.
- **Blocked while a run is in flight**, matching the topic box
  (`guardTopic` returns null when `running`) and the global bank's
  disabled investigate button — `rootThunk` switches the reader to the
  new tree the moment it starts, which would yank you out of whatever is
  currently growing. The button renders `disabled` with a title saying
  why, rather than vanishing.
- **Offered for long selections too**, unlike add/define/dig. A
  highlighted sentence is often a *better* topic than a single term, and
  `selInfo` already caps a selection at 300 characters, so the topic
  can't run away.
- **The chip's max-width needed loosening** from 34rem to 42rem: six
  buttons measure ~590px, so the old cap forced a wrap even on a wide
  desktop. It still wraps to two rows at phone width (verified at a
  366px cap: 58px tall, nothing clipped).
- 57 assertions now run against the real page, including that the new
  tree is a root and not a branch, that its glossary starts empty, that
  the tree you came from is untouched, and that the stub tutor's answer
  lands in the new tree.

### Candidates rejected (this cycle)
- **Carrying a provenance link back to the source tree** — tempting, but
  it's a new tree field to merge, sync, and export for something the tree
  list already makes findable, and it quietly contradicts "separate".
- **A confirm dialog before spending** — a full investigation is several
  model calls, but the global bank sets the precedent of starting one on
  a single tap, and `stop` is always right there in the status bar.
- **Queueing it behind a running investigation** instead of disabling —
  `enqueue` would accept it, but the reader would be teleported to a new
  tree minutes later with no idea why.

---

## Feature 41 — the glossary is strictly what you put in it

*(user-requested: "no words should ever be added automatically to the
glossary — the user should explicitly highlight a word and click 'add to
glossary'", then "add should add to the glossary — define shouldn't — and
remove any automatic route to the glossary".)*

### What it is
Nothing enters the glossary on its own any more. The words tab lists
exactly the terms you added, and the two gestures are cleanly split:

- **➕ add** (new, on the selection chip and on the 🔍 term chip) — files
  the word. No model call, no cost, no definition. The only door in.
- **✎ define** — a *lookup*. It fetches the meaning, shows it, and writes
  nothing. If it was worth keeping, the popover's **➕ add to glossary**
  keeps it *with* the definition already paid for.

Definitions for added terms come from the entry's existing *✎ define it*,
or **define N missing** in a batch — which stops being dead weight and
becomes the natural workflow: add a run of words while reading, backfill
them in one pass.

### Design notes
- **There was exactly one automatic route, and it was derived, not
  stored.** `glossaryItems()` merged every turn's `new_term` with the
  stored `tree.glossary` entries; the storage was always explicit. So the
  fix is a five-line function that returns the stored entries and nothing
  else — the sync, exports, Anki, study sheet, and review deck already
  read `tree.glossary` (and already filtered to entries with a `def`), so
  they needed no change at all.
- **`new_term` stays in the learner protocol.** It still drives loose
  threads, branch labels, and the 🔍 marker in the transcript — it just
  no longer implies an entry. Loose threads become the honest home for
  "words the learner flagged and never chased".
- **The 🔍 chip became the cheap add.** It already sat next to every
  flagged word; making it a one-tap add (and flipping to 📖 *show* once
  the word is in) means the common case doesn't require selecting text.
  Its ➕/📖 icon and outlined-vs-filled pill carry the state.
- **`✕ forget` needed a tombstone.** With every term hand-curated,
  forgetting is a normal correction rather than a rarity — and the sync
  merge unions glossary keys, so a bare delete came straight back from
  another device's copy. That is itself an automatic route into the
  glossary, so it's in scope. `tree.gone` holds `{k, when}` per removed
  key, unioned both ways in `mergeTrees` (a forget on any device sticks);
  a later re-add wins on its `added` stamp. It rides through the CLI
  untouched via `KnowledgeTree.extras`, so no Python change was needed.
- **The selection chip went from four actions to five and stopped
  fitting a phone** (466px measured, vs. 388px before — which already
  overflowed a 390px screen). It now wraps, with the separators redone as
  a 1px grid gap so a wrapped row doesn't start with a stray border.
- **`defineOne`/`defineMissing` fill entries in rather than rebuilding
  them** — a rebuilt entry would have dropped the `src`/`added`/`rev`/
  `reason` fields that now matter, silently resetting a card's review
  schedule.
- Verified against the real page: 38 assertions driven through headless
  Edge over the actual UI — that a tree with three flagged `new_term`s
  shows an empty glossary, that adding costs zero `/api/define` calls,
  that define makes exactly one call and adds nothing while still
  recording the cost, that promoting the lookup costs no second call,
  that a bare term isn't a review card and a defined one is, and that a
  forgotten term survives a `mergeTrees` round trip against a server copy
  that still has it.

### Candidates rejected (this cycle)
- **Keeping `✎ define` as an add, just renaming it** — would have left
  two doors into the glossary with only wording to tell them apart.
- **Dropping the 🔍 chip entirely** — the strictest read of the rule, but
  it throws away the cheapest legitimate add and leaves the learner's
  flagged word as inert text.
- **An undo toast on ✕ forget** — the tombstone makes deletion real
  across devices, which raises the stakes; still, re-adding is two taps,
  and an undo would have to un-tombstone across the sync.

---

## Feature 40 — ✓ skip what you already know

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
A new fold under the topic box, right above **gaps**: list what you've
already got — one per line — before pressing **new** or **full**, and the
learner won't ask about it, the tutor won't re-explain it, and both stay
focused on what's actually still open. No interview, no extra model call —
you're just telling it upfront instead of it figuring it out one diagnostic
question at a time.

### Design notes
- **Not a new mechanism — the existing `gaps` contract, minus the
  interview.** `tree.baseline` (`{text, solid, shaky, gaps, level, focus,
  when}`) and the `kind: "gaps"` learner/tutor prompts already say exactly
  "don't re-ask/re-explain what's solid" — that machinery didn't care
  *how* the baseline was produced, an interview was just the only producer
  that existed. `knownThunk()` builds the identical shape directly from the
  textarea (`solid` = the typed lines, `shaky`/`gaps`/`level`/`focus` all
  empty) and runs the exact same `kind: "gaps"` investigation `gapsThunk()`
  already uses. Zero backend changes — this shipped as 100% frontend, and
  the whole feature is already covered by the existing gaps test suite.
  Bonus for free: **🧭 baseline** in the header reopens a typed list the
  same way it reopens a real assessment, since `viewBaseline()` only ever
  looked at the shape, never at how it was produced.
- **Deliberately a sibling of gaps, not a merge into it.** Could have added
  a "skip the interview" escape hatch inside the gaps dialog itself, but
  that would've meant explaining the tradeoff (a typed list vs. an actual
  diagnosed read, including a level and shaky-belief corrections) inside an
  already-busy interview UI. A separate fold next to it, with its own hint
  pointing at gaps for "a real assessment," keeps each one legible on its
  own and lets the reader pick before committing to either.
- **`known` threads through `cmdNew`/`cmdFull` as a third, optional
  argument** exactly like `source` already does (`takeKnown()` mirrors
  `takeSource()`'s guard-then-consume shape: only cleared once the topic
  guard actually passes, so an empty topic can't silently wipe a
  not-yet-submitted list). When empty, `cmdNew`/`cmdFull` fall through to
  the original `rootThunk` path untouched — existing behavior is exactly
  byte-for-byte preserved when the fold is never opened.
- Verified with the real stack: booted the actual local server, drove the
  real page over the Chrome DevTools Protocol, typed two facts about hash
  tables into the fold, pressed **new** for real, and watched the actual
  simulated learner's own "thinking" say *"ok so i've got the basic setup —
  hash function maps to index, collisions are real. but like... if two
  keys end up in the same slot, what actually happens to them?"* — it
  visibly treated the typed facts as already known and asked about
  collision resolution instead, never once re-asking what a hash function
  is. Also confirmed `tree.baseline` persisted with exactly the typed
  lines as `solid` and everything else empty, and that the header's
  baseline reopener picks it up once the run isn't active (a `running`
  flag is per-tab client state, so a stale check against the same tab
  mid-run doesn't reflect reality — reopening in a fresh tab against the
  synced tree confirmed the button was there all along).

---

## Feature 39 — 🔬 look deeper: the same topic, re-investigated at real depth

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
A **🔬 look deeper** button sits next to **→ next** in the conversation
header, once a conversation is finished — same spot, opposite move. **→
next** picks a *new* concept to build on the tree; **🔬 look deeper** re-runs
the *same* one, much deeper, as a full new investigation (never a single
exchange like ⛏ dig): a fresh child node grows from the one being deepened,
seeded with everything that node already covered so it never repeats
itself, with the simulated learner forced to expert level and the tutor
explicitly told to set its usual brevity/simplicity habit aside for this
one. Verified against the real Copilot backend: the learner's first
question on a "what a mutex is" deepen was *"when you unlock, how does the
OS pick which waiting thread wakes up? is there a fairness guarantee like
FIFO, or is that left to the scheduler?"* — real internals, not a rehash.

### Design notes
- **A new `kind`, threaded exactly like the existing four.** `webapi.py`'s
  `learner_opening()`/`tutor_extra_context()` already switch on
  `body["kind"]` (`root`/`branch`/`followup`/`gaps`); `"deepen"` is a fifth
  branch, backed by two new persona functions
  (`deepen_learner_message`/`deepen_tutor_context`). No new API route, no
  change to `runInvestigation` or the request shape — the existing
  `{kind, topic, digest}` ctx object was already exactly the right shape.
- **Two independent levers for depth, not one.** A system-prompt
  instruction alone wasn't going to be enough — if the tutor's *ambient*
  style is "concise" (hard-capped at ~2 sentences), no amount of "go deep"
  framing survives that constraint. So depth is forced on two axes at
  once: the new node's `learner_level` is hard-set to `"expert"` (a normal
  field on the node object, so it applies regardless of which `kind`
  eventually answers it — see the `rebuildCtx` note below), which changes
  what the *learner* asks; and `deepen_tutor_context()` explicitly tells
  the tutor to set aside whatever brevity habit its current style carries,
  which changes how the *tutor* answers. Neither alone reliably produces
  "really detailed" — a sharp learner question still gets a two-sentence
  answer under "concise" mode without the second lever, and a tutor told
  to elaborate still won't if the simulated learner only ever asks
  beginner questions.
- **Deliberately did NOT force the tutor's `mode`.** The natural instinct
  was `mode: "technical"` for the deepen call, but `runInvestigation`
  spreads `...tutorParams()` *after* `...ctx` in the same object literal,
  so a `mode` on `ctx` would just get silently overwritten by the user's
  own `tutorParams()` — and even fixing that would override a custom
  tutor's whole voice/personality just to get more depth. Used the
  additive `tutor_extra_context()` channel instead (appended after the
  style block, same as every other kind) with an explicit "override your
  usual length habit" instruction — works whether the active tutor is a
  built-in mode or someone's custom one, and doesn't touch a shared
  function's contract to do it.
- **Scoped to the node's OWN digest, not the whole tree's recap.** The ask
  was "given what you already know from THAT chat" (singular) — deliberately
  narrower than `followupThunk`'s tree-wide recap. `conversationDigest(src.turns)`
  on just the node being deepened, not every node in the tree.
- **`rebuildCtx`'s existing branch/followup simplification just... works
  here too, unexamined at first but confirmed correct.** If a deepen
  investigation gets interrupted and resumed later, `rebuildCtx` (which
  already collapses a resumed *followup* into the "branch" context shape,
  per its own comment) does the same for a resumed *deepen* — since both
  set `branch_from_turn` to the parent's last turn number. This is fine:
  `learner_level: "expert"` lives on the node object itself, not inside
  `ctx`, so it survives regardless of which shape `rebuildCtx` picks; only
  the tutor's extra-context wording gets slightly less emphatic
  ("branch"'s "build on them and go deeper" instead of deepen's explicit
  brevity override) on this rare resume-after-interruption path. Chose not
  to special-case `rebuildCtx` for a fifth kind given the project's own
  precedent already treats this exact simplification as acceptable for a
  structurally identical case.
- Verified past the unit tests (`learner_opening`/`tutor_extra_context`
  threading, plus the existing sourced-tree test extended to cover
  `"deepen"`) with the real stack: seeded a completed local tree directly
  on disk (skipping a slow real root investigation), booted the actual
  local server, drove the real page over the Chrome DevTools Protocol,
  confirmed the button only appears once a node is genuinely finished
  (gated on `!canContinue(node)`), clicked it for real, and watched a real
  Copilot-backed investigation begin: correct parent/child linkage, the
  `expert learner` chip, and a first question that was genuinely about
  internals (OS wake-up fairness on unlock) rather than a repeat of the
  original one-liner answer.

---

## Feature 38 — two question banks: local (Shift+Q) and global (q)

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
The question bank split in two, because the two kinds of "I want to ask this
later" are actually different actions. **Shift+Q** still jots a question tied
to the tree/turn you're reading (unchanged: **local** bank, tree.questions,
investigate = one direct answer appended right there). Plain **q** — now
usable from anywhere, even the welcome screen with no tree open — jots a
question into a new **global** bank instead. Investigating a global question
starts a brand-new investigation with the question's own text as the topic,
exactly as if you'd typed it into the topic box and pressed **new**. The
global bank gets its own hub entry in the words tab (**❓ global questions**)
and its own dialog; the command palette lists both jot actions and both
banks. The global bank has no "run all" — each item is a full multi-turn
investigation, not the local bank's single cheap call, so batching several
unattended felt like a materially bigger, less reversible action than the
local bank's "run all" ever was.

### Design notes
- **Swapped which key means what, on request.** The user said they use the
  global one more, so it gets the bare `q` (previously local's key); local
  moved to `Shift+Q`. Worth remembering for future keybinding requests on
  this project: the more-used action gets the lower-friction key, not
  whichever one happened to exist first.
- **A genuinely new store, not a bigger tree.questions.** A global question
  isn't associated with any tree at the time it's jotted (you might not have
  one open at all), so it can't live inside `tree.questions`. Gave it its own
  small synced doc (`globalQDoc`) instead — same shape and lifecycle as the
  existing `tutorsDoc` (custom tutors): `loadGlobalQDoc`/`persistGlobalQDoc`/
  `syncGlobalQFromServer`, localStorage-first with a server round-trip,
  whole-doc last-write-wins. Reusing that exact pattern (rather than
  reinventing sync for a second time in the same app) is what made the
  cross-device story free.
- **Sync reused existing infrastructure end to end, on both backends.**
  `api/tutors.js` turned out to already be "one small JSON doc in the shared
  `docs` table, keyed `settings:tutors`" — and `api/trees.js`'s tree-listing
  query already filters out `id LIKE 'settings:%'`, meaning this exact
  pattern was designed to be reused for more than one settings-like doc from
  the start. `api/global_questions.js` (hosted) and `GlobalQuestionStore`
  (local, mirrors `TutorStore` exactly) are the second user of it —
  `settings:global_questions` / `global_questions.json`. Zero new
  infrastructure on either backend, just a second small doc through the
  same pipe.
- **"As if 'new' was pressed" taken literally.** `globalBankInvestigateThunk`
  is `rootThunk`'s body with the banked question's text standing in for
  whatever would've been typed into the topic box, plus bookkeeping at the
  end to mark the bank entry answered and remember where it landed
  (`treeId`/`node`/`turn`) for a cross-tree jump later (`openSearchHit`, not
  `jumpToTerm` — the result is essentially always a different tree than
  whatever was open when the question was jotted).
- **No "run all" for the global bank — a deliberate omission, not an
  oversight.** The local bank's "run all" is cheap to offer because each
  item is one model call. Every global item is a full learner↔tutor loop
  (same cost/time as pressing "new" by hand); queueing several unattended
  didn't feel like a reasonable default to ship without being asked for it
  specifically. Flagged here in case that's wanted later.
- Verified past the unit tests (`GlobalQuestionStore` round-trip + the same
  validation shape as `TutorStore`) with the real stack: booted the actual
  local server, drove the real page over the Chrome DevTools Protocol —
  dispatched a synthetic `q` keydown with **no tree open at all** and
  confirmed the global capture bar still opens (the local one requires a
  read tutor turn; the global one must not), saved a question, confirmed it
  landed in `/api/global_questions` on the server, opened the global bank
  dialog and confirmed the row rendered, then actually pressed **new** for a
  real topic, waited for the real investigation's first turn, and confirmed
  `Shift+Q` still opens the local capture bar exactly as before once a
  tutor-answered turn exists to attach it to.

---

## Feature 37 — ⚙ local settings: the tutor can ground itself in your own systems

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why. Went
through a design pivot mid-flight after the first cut shipped — see below —
this entry describes the final shape.)*

### What it is
In `learn --web` (the Copilot CLI transport), the tutor's Copilot session
already got read-only filesystem tools (`view`/`grep`/`glob`), but nothing
told it so, nothing let it reach further than "look around the home
directory," and it couldn't touch skills, `AGENTS.md`, or MCP servers at
all — no way to point it at proprietary material like a team's Confluence.
A new **⚙ local settings** button (header, this mode only) opens a panel
to: swap the model per role (dropdown of common ones, plus "other…" for
anything not listed — the CLI has no way to enumerate what's actually
available) and pick a reasoning effort, no env vars or restart; name one
project directory of the operator's own code or notes the tutor should
check first; and turn on whichever of the operator's own already-registered
MCP servers the tutor may call before answering, via a checklist — a
one-click **+ set up confluence** runs `copilot mcp add` for Atlassian's
official remote server on their behalf (OAuth in a browser tab on first
use, nothing to type in), anything else the operator registers themselves
with `copilot mcp add` shows up in the checklist too. The tutor also now
gets `skill` and its normal `AGENTS.md`/custom instructions — same as any
other `copilot` session on the machine — while shell and write access stay
off. Everything (except the MCP servers themselves) saves to
`local_settings.json` next to the knowledge folder and takes effect on the
next reply, no restart.

### Design notes
- **The system prompt was the actual gap, not the tool grant.** The tutor
  already had `--allow-all-paths` and the read tools; `TUTOR_NO_TOOLS`
  ("do not use any tools or the filesystem") was simply the only clause
  `tutor_system()` ever appended for the web path, hosted or local, so the
  model was told not to touch tools it had. Fixed at the root: a new
  `grounding` kwarg on `tutor_system()` swaps that clause for
  `local_grounding_system()`'s text (what it has, when to bother looking,
  never narrate the lookup) instead of leaving both messages in the prompt
  and hoping the model reconciles them.
- **Hosted stays provably untouched, not just "should be fine."**
  `handle_tutor`/`model_routes` gained an optional `grounding` /
  `tutor_grounding` parameter that defaults to `None`; api/index.py never
  passes it, so `tutor_system(diagrams=False, grounding=None)` — the exact
  hosted call — is asserted byte-identical to the pre-feature prompt in
  `test_tutor_grounding()`. Bolting a second, unrelated concern onto a
  shared route handler is exactly the kind of change that leaks sideways if
  you don't pin the "untouched" case down as a test, not just a claim.
- **`tutor_grounding` is a callable, not a string.** Settings (code
  directory, which MCP servers are on) can change mid-session from the
  panel; `ROUTES = model_routes(...)` is built once at import. Passing
  `copilot_backend.grounding_text` (the function itself) instead of its
  result means every tutor turn re-reads the live settings, confirmed by a
  test that a stub grounding function is called once per request, not once
  total.
- **MCP servers are read from the real `~/.copilot/mcp-config.json`, not
  redefined in this app — a mid-flight pivot.** The first cut let the panel
  author full server JSON (command/url/headers/env) into `local_settings.json`
  and injected it per-call via `--additional-mcp-config`. Asked *why not
  just use the config `copilot mcp add` already writes*, and the honest
  answer was: no good reason — this app still has to know a server's *name*
  to add it to the tutor's `--available-tools` allowlist (that part is
  inherently app-level state), but the server *definition* was pure
  duplication of something the CLI already manages, and it meant a checkbox
  in this app could never see servers set up any other way, or interact
  cleanly with an operator's existing `copilot` setup — which was the whole
  point once skills and custom instructions were also in scope. Replaced
  with `copilot_backend.list_global_mcp_servers()` (`copilot mcp list
  --json`) feeding a checklist, `add_global_mcp_server()` (`copilot mcp
  add`) behind the one-click Confluence button, and
  `local_settings.mcp_servers` shrunk to `{name, enabled, note}` —
  references, never definitions. `--additional-mcp-config` is gone entirely;
  registered servers load the way the CLI already loads them for everyone.
- **Confluence needed zero secret-handling code either way.** Atlassian's
  own remote MCP server (`https://mcp.atlassian.com/v1/mcp/authv2`) handles
  auth itself via OAuth the first time the tutor actually calls it — a
  browser tab opens, the operator signs in, done. True before and after the
  pivot; only *where* the URL gets registered changed (this app's JSON vs.
  a real `copilot mcp add` call).
- **Skills and custom instructions: opened up, not left as a maybe.** Initial
  build kept `--no-custom-instructions` on the tutor and never exposed the
  `skill` tool, reasoning that skills can have side effects beyond a
  read-only lookup. Asked directly, and the answer was clear: these are the
  operator's own already-trusted config, useful for answering better, and
  not something a question-answering session is realistically going to
  misuse. `--no-custom-instructions` moved to the learner/glossary branch
  only (those two must stay uncontaminated fixed personas — picking up the
  operator's own coding instructions would break the simulation, not help
  it); the tutor's `--available-tools` grew a `skill` entry. Shell and write
  access were never on the table either way.
- **Settings apply through a live overlay, not a restart.** `copilot_backend`
  holds a lock-guarded settings dict `configure()` replaces wholesale;
  `effective_model()`/`effective_effort()` check it before falling back to
  the existing env vars, so nothing about the CLI-flag-building code needed
  to change shape, only where its inputs come from. Confirmed the *default*
  state (nothing ever saved) reproduces the exact previous argv byte for
  byte — the pre-existing tool-policy test still passes untouched.
- **Strict on save, lenient on load.** `local_settings.sanitize(strict=...)`
  raises a message fit to show the person who typed the bad value when the
  panel POSTs (a bad effort, a code_dir that isn't a real directory, a
  duplicate server name), but silently drops garbage when reading the file
  back at startup — a hand-edited or stale `local_settings.json` must never
  stop the server from booting.
- **A real race, found only by driving the real page.** `GET
  /api/local_settings` now shells out to `copilot mcp list --json` to build
  the checklist — measured close to a second, cold. `openLocalSettings()` is
  `async`; its `setModelField()`/`$("lscodedir").value = ...` calls run
  *after* that `await fetch(...)` resolves. Open the panel, and — before that
  fetch lands — pick a model: the panel looked fine, but the slow response
  landing afterward silently overwrote the pick back to blank, because the
  same in-flight `openLocalSettings()` call resumes and repopulates
  everything from the (already-stale) server response. Unit tests couldn't
  have caught this — it only exists as a timing gap in a real browser
  against a real slow endpoint. Found it by scripting the actual page over
  the Chrome DevTools Protocol and noticing a selection didn't stick; fixed
  by disabling the whole form (cancel excepted) between open and populate,
  which closes the race for a real user categorically rather than papering
  over one observed timing.
- Verified past the unit tests with the real stack throughout: booted the
  actual local server, drove the real page over CDP (headless Edge) —
  clicked ⚙, registered Confluence for real (`copilot mcp add` really ran,
  really showed up in `copilot mcp list`), saved with a fake directory and
  watched the server reject it with the exact validation message inline,
  saved for real and confirmed `/api/local_settings` came back with the
  model, directory, and enabled server persisted, and confirmed the loading
  race above both existed and was fixed by watching `disabled` flip and a
  selection survive a full wait cycle. Also checked the row-builder's
  HTML-escaping directly in Node (a name/note containing `"><script>` cannot
  break out of the row markup).

---

## Feature 36 — flashcards become a deliberate act, with a reason

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
Previously every term the simulated learner flagged as unfamiliar
(`new_term`) silently became a flashcard the instant it appeared —
`autoDefine()` fired a definition call for it with zero input from the
reader, on top of the same thing happening again if you manually hit
**✎ define**. Now nothing gets carded automatically: `new_term` still
lists a term in the words tab (undefined, same as any term whose "define
it" you haven't clicked yet), but the only way a card gets its content is
a deliberate act. **✎ define** is unchanged — still the instant one-click
plain-definition fast path. Selecting text now also offers **+ flashcard**
(for both short, term-like selections AND longer passages, unlike define/
dig which stay short-only): it folds out four categories — definition /
purpose / example / how it works — the model drafts whichever angle you
pick, and the draft lands in an editable box with **add** / **cancel**.
Nothing is saved until you hit add, so you can tweak the wording first.
A term can now carry more than one reasoned card (its plain definition
*and* a purpose card, say) — the words tab, review deck, and anki/study-
sheet exports all show a small badge for any card whose reason isn't a
plain definition.

### Design notes
- **Killed the automatic path, not just added a new one.** The actual
  ask was "give control to the user" — leaving `autoDefine()` firing on
  every turn and bolting a picker on top would still have flooded the
  glossary with unwanted cards. Deleted the call site and the now-dead
  function outright; `glossaryItems()` already derives the words-tab
  listing straight from `turn.new_term`, independent of `tree.glossary`,
  so undefined terms keep showing up with a manual "define it" — no
  regression there, just no more silent card creation.
- **Compound glossary keys, no new top-level data structure.** A
  "definition" card keeps the classic bare `term.toLowerCase()` glossary
  key (every existing consumer — underlines, anki, study sheet, CLI
  markdown/HTML export, sync merge — keeps working untouched, and old
  trees need no migration: a missing `reason` field just reads as
  "definition"). Any other reason files under `term::reason` instead, so
  it can't collide with the term's plain definition. `glossaryItems()`
  turned out to already support this for free — its "entries whose turn
  was pruned" pass iterates every raw key in `tree.glossary`, not just
  ones derived from `new_term`, so a compound key was never filtered out.
  Confirmed this rather than assumed it, by reading the function before
  writing the popover.
- **Backend prompt is reason-parameterised, not four separate prompts.**
  `GLOSSARY_SYSTEM` now describes answering "whichever angle you're
  given"; `GLOSSARY_REASONS` in `personas.py` holds the one-line
  instruction per angle, and `define_message()` takes an optional
  `reason` (default `"definition"`, so the CLI's own callers and the
  existing test fixture didn't need touching). `handle_define()` falls
  back to `"definition"` for a missing or unrecognised reason — the API
  boundary doesn't trust the client's string.
- **In-text popover (tap a dotted-underlined word) deliberately left
  single-reason.** `showGloss()` looks up the bare key only, so it still
  shows just the plain definition wherever one exists — reasoned cards
  surface in the words tab and review deck instead. Extending the
  in-text popover to cycle through multiple reasons for the same word
  felt like scope beyond what was asked for; flagged here in case that's
  wanted later.
- Verified with a 19-assertion headless browser run driving the real UI
  (Chromium DOM, stubbed `/api/define`): selection chip shows the new
  button and its category fold-out; the reason actually reaches the
  backend request; the generated draft is editable and the *edited* text
  (not the model's first draft) is what gets saved; the compound key
  lands correctly; the bare-term key is confirmed to NOT exist afterward
  (no auto-card leaked in); the words tab and review card both show the
  reason badge; and `+ flashcard` stays offered on a long passage while
  define/dig correctly disappear.

---

## Feature 35 — 🗣 explain it back keeps probing after the first round

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
Previously, every "explain it back" send was stateless: the tutor graded
whatever was in the box against the conversation digest from a cold
start, with zero memory of the previous round's feedback or its
probing question — "aim your next try at the gap and send again" meant
re-explaining the whole thing into the same box and hoping the edit
addressed it. Now, once a round comes back **≈ close** or **△ gappy**
(anything but clean), the box turns into answering that one question:
placeholder and button both change ("Take on the question above…" /
**answer**), the box is left empty for a short, targeted reply instead
of a wall of text, and the reply is sent along with the thread's
history since the last **✓ clean** (capped at 5 rounds). The tutor's
feedback is judged against the WHOLE exchange, not the latest reply
alone — crediting what's now resolved, narrowing on whatever nuance is
still missing, and pushing further with a follow-up in the SAME line of
inquiry rather than a fresh unrelated question — until it reaches clean
(placeholder/button reset to the fresh-explanation state) or the
learner stops. **⤳ chase it** is unchanged — it still hands the
question to the real conversation instead, for when you'd rather have
the tutor just answer it there.

### Design notes
- **No new data shape.** `tree.teach` already stored a flat, ordered
  array of attempts per node (`{node, when, text, right, missing,
  question, verdict}`) to drive the trail UI and the spaced-repetition
  ladder — a "thread" is just the trailing run of that same array back
  to (not including) the last clean verdict. `threadHistory()` computes
  it client-side; nothing new syncs, merges, or exports differently.
- **Wire-shape mismatch caught by the headless test, not by hand.** The
  stored attempt's explanation field is `text` (chosen to stay generic
  across the app's other authored-text fields); the API's top-level
  field is `explanation`. `threadHistory()` has to map one to the other
  when building the outgoing history — missed this on the first pass,
  and the browser probe threw on it immediately (`history[0].explanation`
  was `undefined`), which is exactly the kind of wiring bug a
  behavioural test catches and a syntax check can't.
- **Backend change is additive and bounded.** `teachback_message()`
  gained an optional `history` parameter (old call sites — the CLI has
  no teach-back path, so only this one — are unaffected by the default
  `None`); `handle_teachback()` clips it the same defensive way as the
  `interview` route already clips its exchange list (last 6, each field
  capped). No prompt behaviour changes when `history` is empty, verified
  by asserting `"CONTINUING" not in` the built message in that case.
- **Found and fixed a latent test-suite gap while in this file:**
  `test_handle_interview` and `test_handle_teachback` were both defined
  but never called from `tests/test_web_helpers.py`'s `__main__` block —
  my new continuation-mode assertions would have silently never run.
  Wired both into the runner.
- Verified with the now-running `test_handle_teachback` (one-shot
  framing unchanged, continuation framing includes prior explanation +
  question, malformed/empty history entries dropped, entry count capped)
  and a 15-assertion headless browser run of the real UI: fresh round →
  close verdict → box reframes to answering mode → second round sends
  history → clean verdict → box resets to the fresh-explanation state.

---

## Feature 34 — ❓ question bank

*(user-requested, not picked from the autonomous candidate list — logged
here anyway since it's the running record of what changed and why.)*

### What it is
Press **q** anywhere while reading a conversation and a small floating
bar appears — no dialog dimming the page, no scrolling away — asking
what you're wondering. It tags itself with whichever turn sits at the
top of the viewport (the same scroll-position heuristic `j`/`k` turn-
hopping already uses), so the question is anchored to the passage that
actually prompted it. Saving doesn't ask the tutor right away: it goes
into that tree's question bank instead, so a stray thought never
interrupts a run in progress. A **❓ questions** button in the
conversation header (shown once the tree has any) opens the bank:
**investigate** answers one question on its own, **run all** queues
every pending one in sequence — exactly like `full` queues its four
follow-ups, just reusing the existing queue instead of adding a second
one. Either path rides the same single "ask the tutor directly with
this node's context" call as 🧑 ask-the-tutor-yourself / ⛏ dig, so
investigating a banked question is one real model call, appended to
the conversation as your own turn (`user: true`), never one the
simulated learner sees. Answered questions fold under a disclosure with
a jump back to the Q&A they became; discarding a pending one just
drops it. Everything lives on `tree.questions` — travels in
`.know.json`, syncs last-write-wins-per-field like highlights (union by
id, with "answered" a one-way flip so a lagging device can't
resurrect a question the other side already answered).

### Design notes
- **Scoped to one tree, not the profile.** The docket and highlights hub
  aggregate across every tree in the active profile, and an early draft
  of this feature did too — until tracing the "run all" path showed it
  would process nodes in trees other than the one on screen. The app's
  `activity` object (drives the "tutor is answering…" inline indicator)
  is keyed by `nodeId` alone, with no `treeId`, because every existing
  queue thunk (root/branch/follow-up/ask) only ever touches the
  currently open tree — node ids aren't unique across trees, so a
  background answer in tree B could paint its "answering…" spinner
  under the wrong node if tree A (open, unrelated) happened to reuse
  that id. Keeping the bank per-tree sidesteps the mismatch entirely by
  never introducing cross-tree background execution — lower risk than
  patching a shared global that every other thunk also depends on.
- **Investigating one rides `askThunk`'s exact path**, parameterised by
  a question id instead of the ask box's live input, and marks the bank
  entry answered in the same save. No backend changes at all — the
  `/api/tutor` route it calls already existed for the ask box and ⛏ dig.
- Verified with a 25-assertion headless run (capture → tag → save →
  Escape-cancels vs Enter-saves → header count → bank rows → individual
  investigate through the real queue and stub tutor → run-all →
  discard → jump-to-context → Esc closes both panels → the merge
  union/answered-wins logic) plus the existing `test_web_helpers.py`
  suite and a CSS/JS syntax and brace-balance pass.

---

## Feature 33 — 📚 ground it in your own material

### What it is
A **ground it in your own material** fold under the topic box: paste a
passage — a textbook section, an article, lecture notes — and pressing
**new** or **full** grounds the whole tree in it. The simulated
learner's opening (and every branch/follow-up/gaps opening) gets the
passage prepended before the task, so its questions stay anchored to
what it actually says; the tutor's system prompt gets a matching
grounding block telling it to answer from the passage, use its
terminology, and say plainly when the passage is wrong or
oversimplified. The passage lives on `tree.source` — travels in
`.know.json` via the existing extras round-trip, syncs last-write-wins
like `note`, is quoted at the top of both exports — and a **📚 source**
button appears in the conversation header (and ⌘K) on a grounded tree
to reopen or correct it, taking effect from the next turn. Capped at
6000 characters, enforced on both ends.

### Why this one
- The audit's honest gap: every other production surface in the app —
  the CLI's diagram pen, the survey map, the gaps interview — starts
  from the tutor's general knowledge. But the actual use case "I have a
  reading and I don't get it" (a student with an assigned chapter, a
  practitioner with a paper) had no way in; the closest existing tool,
  the CLI's `seeplusplus` code reader, is source code only and
  terminal-only. Grounding the whole learner↔tutor loop in a pasted
  passage is a different, complementary way to start a tree — read *with*
  a tutor instead of asking one cold.
- Threading was genuinely low-risk because every conversation kind
  already funnels through one function: `runInvestigation(tree, node,
  ctx)` builds every learner and tutor call for root, branch, follow-up,
  and continued conversations, so grounding is one `if (tree.source)
  ctx = {...ctx, source: tree.source}` at its top — not four call
  sites. Ask-the-tutor is the one path outside that loop and got its
  own one-line addition. Server-side, `source_of()` is one new field
  read in `learner_opening()`/`tutor_extra_context()`, which every
  route already calls.
- Free data round-trip: `KnowledgeTree.from_dict`/`to_dict` already
  preserve unrecognised top-level keys verbatim (`extras`) — the
  mechanism Feature 9 built for exactly this — so `source` survives the
  CLI without a single knowledge.py schema change. Only the two
  exporters needed a two-line addition to surface it to a reader.
- Verified with 30 assertions total: 16 headless (source threads into
  the learner AND tutor call bodies, box clears after starting, header
  chip appears/edits/persists, Esc closes, ask-the-tutor inherits it,
  an unsourced tree sends no `source` key at all, a failed topic guard
  doesn't wipe an unsubmitted paste, the client-side cap) and 14 Python
  (passage lands before the task text in every conversation kind, the
  tutor block reads "Ground your answers", it composes correctly after
  each kind's own context, the server-side cap, junk-input tolerance).

### Candidates rejected (this cycle)
- **Import a PDF/URL as source material** — real value, but fetching
  and extracting text server-side is a much bigger surface (fetch
  policy, PDF parsing, size limits) for a first cut; paste covers the
  common case (copy from wherever you're reading) at zero new risk.
- **A dedicated "study a source" start mode** (5th button beside new
  /full/survey/gaps) — considered, but the fold under the existing
  topic box was the smaller, more discoverable surface: it composes
  with new/full instead of forking a fifth path, and survey/gaps keep
  their own specialised openings untouched.
- **Highlighting which passage sentence an answer came from** — a nice
  future layer once the grounding itself has proven its worth; the
  tutor already free-quotes the passage in prose today.

---

## Feature 32 — 📜 study sheet: the profile compiled into one document

### What it is
A **study sheet** button in the file row (and ⌘K): one Markdown
document compiling the whole active profile into the sheet you'd
actually revise from — per tree (newest first): **my notes**, the
**best explanation** you gave of each conversation (best verdict wins,
latest among equals, tagged ✓/≈/△), and the passages you
**highlighted** (quoted, whitespace-collapsed) — then one merged
**alphabetical glossary** of every defined term across the profile, the
newest tree's wording winning a collision. Saved through the existing
`download()` path, so phones get the share sheet; the filename carries
the profile (`computer-science-study-sheet.md`). Disabled until the
profile has anything worth compiling.

### Why this one
- The audit checked first (the Feature 11 lesson, which caught "retry
  the missed" already existing this same cycle): every export today is
  per-tree and transcript-centric. Nothing compiled the *user-produced*
  layer — notes (F4), highlights (F5), teach-back explanations (F25) —
  across trees, which is exactly what revision before an exam wants:
  your own words first, the reference glossary second, the transcripts
  not at all. It's the Readwise insight (what you marked is the
  valuable residue) applied to everything this app already collects.
- Entirely client-side over existing data — no model calls, no backend,
  no new storage; the one design decision (best-verdict-then-latest
  attempt selection) reuses the teach-verdict semantics F28 defined.
- Verified with a 14-assertion headless run: section order, verdict
  selection, whitespace collapsing, alphabetical merge with
  newest-wins collision, undefined-term exclusion, profile scoping,
  all-trees fallback, palette entry, and the download filename.

### Candidates rejected (this cycle)
- **Retry missed quiz questions** — chosen first, then found already
  shipped (`retryQuiz(true)`, subset runs excluded from the score
  history); the audit caught it before any duplicate work.
- **PWA "update available" toast** — checked sw.js: navigations are
  network-first, deploys land on the next load; there is no staleness
  to toast about.
- **🔊 listen through a whole tree** — parked again; still waiting for
  evidence the per-conversation listen flow is hitting its ceiling.

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
