"""Transport-agnostic route handlers shared by every web backend.

The Vercel function (api/index.py, Anthropic API) and the local server
(localweb.py, Copilot CLI) both serve the same routes with the same request
and response shapes; only the model transport differs. Each handler takes the
parsed JSON body plus a ``call_model`` callable:

    call_model(system, messages, role, effort=None, max_tokens=16000)
        -> (text, cost)

``role`` is "learner", "tutor", or "glossary" — the backend maps it to a
concrete model (and, for the Copilot backend, a tool policy). ``cost`` is
whatever unit the backend counts in (USD for the API, premium requests for
Copilot); handlers just pass it through.
"""

from __future__ import annotations

import json
import re

from . import gemini_images
from .knowledge import KnowledgeTree, conversation_digest
from .personas import (
    EXAM_KINDS,
    EXAM_SYSTEM,
    FACT_KINDS,
    FACTS_SYSTEM,
    GLOSSARY_REASONS,
    GLOSSARY_SYSTEM,
    ILLUSTRATE_SYSTEM,
    INTERVIEW_FINISH,
    INTERVIEW_SYSTEM,
    LEARNER_LEVELS,
    MARK_EXAM_SYSTEM,
    NEXT_CONCEPT_SYSTEM,
    ORDER_QUESTIONS_SYSTEM,
    QUIZ_SYSTEM,
    SUGGEST_QUESTIONS_SYSTEM,
    SURVEY_SYSTEM,
    TEACHBACK_SYSTEM,
    TUTOR_MODES,
    branch_learner_message,
    branch_tutor_context,
    deepen_learner_message,
    deepen_tutor_context,
    define_message,
    exam_message,
    feedback_message,
    first_learner_message,
    followup_learner_message,
    followup_tutor_context,
    gaps_learner_message,
    facts_message,
    gaps_tutor_context,
    illustrate_message,
    interview_budget_note,
    interview_opening,
    learner_system,
    mark_exam_message,
    next_concept_message,
    order_questions_message,
    quiz_message,
    session_brief_learner_context,
    source_learner_context,
    source_tutor_context,
    suggest_questions_message,
    survey_message,
    teachback_message,
    tutor_system,
)
from .render import space_sentences
from .simulator import clean_term, extract_turn, first_json_object


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# prompt reconstruction — mirrors run_conversation() in simulator.py
# --------------------------------------------------------------------------- #
SOURCE_MAX = 6000


def source_of(body: dict) -> str:
    """The passage a sourced tree is grounded in, capped server-side."""
    s = body.get("source")
    return s.strip()[:SOURCE_MAX] if isinstance(s, str) else ""


def learner_opening(body: dict, brief: str = "") -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        msg = branch_learner_message(
            body["topic"], body.get("breadcrumb", ""), body.get("digest", ""),
            body.get("branch_q", ""), body.get("branch_a", ""), body.get("focus", ""),
        )
    elif kind == "followup":
        msg = followup_learner_message(
            body["topic"], body.get("recap", ""),
            body.get("concept", ""), body.get("opening_question", ""),
        )
    elif kind == "gaps":
        msg = gaps_learner_message(
            body["topic"], body.get("baseline", ""),
            body.get("focus", ""), body.get("opening_question", ""),
        )
    elif kind == "deepen":
        msg = deepen_learner_message(body["topic"], body.get("digest", ""))
    else:
        msg = first_learner_message(body["topic"])
    src = source_of(body)
    if src:
        # passage first; the task (and its output contract) stays last
        msg = f"{source_learner_context(src)}\n\n{msg}"
    if brief:
        # scenery goes above everything: the passage (when there is one) is
        # what the learner is studying, this is only the room it stands in
        msg = f"{session_brief_learner_context(brief)}\n\n{msg}"
    return msg


def anchor_question(body: dict) -> str:
    """The one question THIS investigation exists to answer.

    feedback_message() restates it to the learner every turn, which is what
    keeps a session from wandering off into whatever the tutor's last reply
    happened to mention. It is not always body["topic"]: on a branch, followup
    or gaps node the topic is the ROOT of the whole tree while the node itself
    was opened to answer something narrower, and anchoring those to the root
    would drag the learner straight back out of the thread.
    """
    kind = body.get("kind", "root")
    topic = (body.get("topic") or "").strip()

    def field(name: str) -> str:
        v = body.get(name)
        return v.strip() if isinstance(v, str) else ""

    if kind == "branch":
        # No explicit focus means the learner chose its own thread on turn 1,
        # so fall back to the answer it opened the branch to dig into.
        branch_a = field("branch_a")
        return field("focus") or (
            f'going deeper on this point: "{branch_a[:160]}"' if branch_a else topic
        )
    if kind in ("followup", "gaps"):
        return field("opening_question") or field("concept") or field("focus") or topic
    return topic


def tutor_extra_context(body: dict) -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        extra = branch_tutor_context(body.get("digest", ""), body.get("branch_a", ""))
    elif kind == "followup":
        extra = followup_tutor_context(body.get("recap", ""), body.get("concept", ""))
    elif kind == "gaps":
        extra = gaps_tutor_context(body.get("baseline", ""))
    elif kind == "deepen":
        extra = deepen_tutor_context(body.get("digest", ""))
    else:
        extra = ""
    src = source_of(body)
    if src:
        block = source_tutor_context(src)
        extra = f"{extra}\n\n{block}" if extra else block
    return extra


def turn_json(turn: dict) -> str:
    """The learner's turn re-serialised as the JSON object it originally
    emitted — used as the assistant side when rebuilding its conversation."""
    return json.dumps(
        {
            "thinking": turn.get("thinking") or "",
            "new_term": turn.get("new_term") or None,
            "action": turn.get("action") or "",
            "confidence": turn.get("confidence"),
            "done": bool(turn.get("done")),
        },
        ensure_ascii=False,
    )


def handle_learner(body: dict, call_model, brief: str = "", brief_cost: float = 0.0) -> dict:
    """`brief` is local-mode only: an orientation on the anchored Copilot
    session, so the learner recognises the domain's vocabulary instead of
    misreading a term and aiming the whole investigation at the wrong thing.
    `brief_cost` is whatever producing it cost, folded into this turn so the
    header stays honest about what was spent."""
    level = body.get("level")
    if level not in LEARNER_LEVELS:
        level = "student"
    messages = [{"role": "user", "content": learner_opening(body, brief)}]
    anchor = anchor_question(body)
    for t in body.get("turns", []):
        messages.append({"role": "assistant", "content": turn_json(t)})
        messages.append({"role": "user", "content": feedback_message(t.get("tutor", ""), anchor)})
    text, cost = call_model(learner_system(level), messages, "learner")
    data = extract_turn(text)
    return {
        "thinking": (data.get("thinking") or "").strip(),
        "new_term": clean_term(data.get("new_term")),
        "action": (data.get("action") or "").strip(),
        "confidence": data.get("confidence"),
        "done": bool(data.get("done")),
        "cost": cost + brief_cost,
    }


# A part tag: a short bracketed label alone at the start of a line, e.g.
# "[why]" or "[so where does the copy live?]". Purely numeric labels (citation
# style, "[1]") don't count, and code fences are skipped while scanning.
_PART_TAG = re.compile(r"^\s*\[([^\[\]\n]{2,60})\]\s*(.*)$")


def split_tutor_parts(text: str) -> list:
    """Split a tutor reply on its [label] markup lines into
    [{"label": str, "text": str}, ...]. The opening (untagged) answer comes
    back as a part with label "". Returns [] when there is no markup at all."""
    parts = [{"label": "", "lines": []}]
    in_code = False
    for line in (text or "").split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            parts[-1]["lines"].append(line)
            continue
        m = None if in_code else _PART_TAG.match(line)
        label = (m.group(1).strip() if m else "")
        if m and label and not label.isdigit():
            parts.append({"label": label, "lines": [m.group(2)] if m.group(2).strip() else []})
        else:
            parts[-1]["lines"].append(line)
    out = []
    for p in parts:
        body = "\n".join(p["lines"]).strip()
        if body or p["label"]:
            out.append({"label": p["label"], "text": body})
    if len(out) < 2:
        return []
    return out


def handle_tutor(body: dict, call_model, grounding: "str | None" = None) -> dict:
    action = (body.get("action") or "").strip()
    if not action:
        raise ApiError("missing 'action'")
    mode = body.get("mode")
    if mode not in TUTOR_MODES:
        mode = "balanced"
    custom = body.get("custom_style")
    if not isinstance(custom, str):
        custom = None
    elif len(custom) > 4000:
        custom = custom[:4000]
    system = tutor_system(mode=mode, custom_style=custom, segments=True,
                          grounding=grounding)
    extra = tutor_extra_context(body)
    if extra:
        system += f"\n\n{extra}"
    messages = []
    for t in body.get("turns", []):
        if t.get("action") and t.get("tutor"):
            messages.append({"role": "user", "content": t["action"]})
            messages.append({"role": "assistant", "content": t["tutor"]})
    messages.append({"role": "user", "content": action})
    text, cost = call_model(system, messages, "tutor")
    parts = split_tutor_parts(text)
    if not parts:
        return {"tutor": space_sentences(text), "cost": cost}
    # the stored/plain answer is the parts joined without their tags, so the
    # learner sim, digests, search, and exports all keep seeing clean text
    for p in parts:
        p["text"] = space_sentences(p["text"])
    clean = "\n\n".join(p["text"] for p in parts if p["text"])
    return {"tutor": clean, "parts": parts, "cost": cost}


def handle_next_concept(body: dict, call_model) -> dict:
    message = next_concept_message(
        body.get("root_topic", ""), body.get("covered", []), body.get("recap", "")
    )
    text, cost = call_model(
        NEXT_CONCEPT_SYSTEM, [{"role": "user", "content": message}], "tutor"
    )
    pick = first_json_object(text)
    if not isinstance(pick, dict) or not str(pick.get("concept") or "").strip():
        pick = None
    return {"pick": pick, "cost": cost}


INTERVIEW_MAX_Q = 6


def _clean_assessment(data: dict) -> dict:
    def items(key):
        raw = data.get(key)
        out = [str(x).strip()[:200] for x in (raw if isinstance(raw, list) else [])
               if str(x).strip()]
        return out[:6]

    level = str(data.get("level") or "").strip().lower()
    if level not in LEARNER_LEVELS:
        level = "student"
    focus = str(data.get("focus") or "").strip()[:80]
    if not focus:
        raise ApiError("the tutor returned no usable read — try again", 502)
    return {
        "solid": items("solid"), "shaky": items("shaky"), "gaps": items("gaps"),
        "level": level, "focus": focus,
        "opening_question": str(data.get("opening_question") or "").strip()[:300],
    }


def handle_interview(body: dict, call_model) -> dict:
    """One step of the gaps interview: given the transcript so far, the tutor
    either asks the next diagnostic question or concludes with the assessment
    (what's solid / shaky / missing, evident level, and where to aim first)."""
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise ApiError("missing 'topic'")
    exchanges = []
    for ex in (body.get("exchanges") or [])[:INTERVIEW_MAX_Q + 2]:
        if not isinstance(ex, dict):
            continue
        q = str(ex.get("q") or "").strip()[:400]
        a = str(ex.get("a") or "").strip()[:2000]
        if q and a:
            exchanges.append({"q": q, "a": a})
    finish = bool(body.get("finish")) or len(exchanges) >= INTERVIEW_MAX_Q
    if finish and not exchanges:
        raise ApiError("nothing to assess yet")
    messages = [{"role": "user", "content": interview_opening(topic[:200])}]
    for i, ex in enumerate(exchanges):
        messages.append({"role": "assistant",
                         "content": json.dumps({"question": ex["q"]}, ensure_ascii=False)})
        content = f'The learner answers:\n"""\n{ex["a"]}\n"""'
        if i == len(exchanges) - 1:
            content += "\n\n" + (INTERVIEW_FINISH if bool(body.get("finish"))
                                 else interview_budget_note(len(exchanges), INTERVIEW_MAX_Q))
        messages.append({"role": "user", "content": content})
    text, cost = call_model(INTERVIEW_SYSTEM, messages, "tutor")
    data = first_json_object(text)
    if isinstance(data, dict) and isinstance(data.get("assessment"), dict):
        return {"assessment": _clean_assessment(data["assessment"]), "cost": cost}
    question = data.get("question") if isinstance(data, dict) else None
    if isinstance(question, str) and question.strip() and not finish:
        return {"question": question.strip()[:400], "cost": cost}
    raise ApiError("the tutor lost the thread of the interview — try again", 502)


def handle_teachback(body: dict, call_model) -> dict:
    """The Feynman step: the learner explains a conversation back in their
    own words; the tutor answers with what's solid, the one thing missing,
    and one probing question. Feedback, not a grade — content only.

    An optional 'history' carries the whole conversation about this node so
    far (it never resets — a "clean" verdict is praise for that round, not
    a memory wipe, since the tutor keeps a real follow-up question on the
    table regardless): when present, the learner's 'explanation' is their
    reply to the tutor's last question, not a fresh restart, so the tutor
    can keep pushing on the same nuance instead of re-grading from zero."""
    explanation = (body.get("explanation") or "").strip()
    if not explanation:
        raise ApiError("missing 'explanation'")
    history = []
    for h in (body.get("history") or [])[:10]:
        if not isinstance(h, dict):
            continue
        exp = str(h.get("explanation") or "").strip()[:4000]
        if not exp:
            continue
        history.append({
            "explanation": exp,
            "right": str(h.get("right") or "").strip()[:1200],
            "missing": str(h.get("missing") or "").strip()[:1200],
            "question": str(h.get("question") or "").strip()[:400],
        })
    message = teachback_message(
        (body.get("topic") or "").strip()[:200],
        (body.get("label") or "").strip()[:120],
        (body.get("digest") or "").strip()[:24000],
        explanation[:8000],
        history=history,
    )
    text, cost = call_model(TEACHBACK_SYSTEM, [{"role": "user", "content": message}], "tutor")
    data = first_json_object(text)
    fb = {}
    if isinstance(data, dict):
        for k in ("right", "missing", "question"):
            fb[k] = space_sentences(str(data.get(k) or "").strip())[:1200]
    if not (fb.get("right") or fb.get("missing")):
        raise ApiError("the tutor returned no usable feedback — try again", 502)
    verdict = str(data.get("verdict") or "").strip().lower()
    fb["verdict"] = verdict if verdict in ("clean", "close", "gappy") else "close"
    return {**fb, "cost": cost}


def handle_define(body: dict, call_model) -> dict:
    """One flashcard entry, on the cheap model. Context is the exchange where
    the learner hit the term, so the answer matches its use there. "reason"
    picks the angle (definition/purpose/example/mechanism); an unknown or
    missing reason falls back to a plain definition, the original behaviour."""
    term = (body.get("term") or "").strip()
    if not term:
        raise ApiError("missing 'term'")
    reason = (body.get("reason") or "definition").strip().lower()
    if reason not in GLOSSARY_REASONS:
        reason = "definition"
    message = define_message(
        term[:120],
        (body.get("topic") or "").strip()[:200],
        (body.get("context") or "").strip()[:4000],
        reason,
    )
    text, cost = call_model(
        GLOSSARY_SYSTEM, [{"role": "user", "content": message}],
        "glossary", effort="none", max_tokens=300,
    )
    data = first_json_object(text)
    definition = ""
    if isinstance(data, dict):
        definition = str(data.get("definition") or "").strip()
    if not definition:
        # a small model may answer in prose despite the contract — take it
        definition = text.strip().strip('"')
    return {"definition": definition[:600], "cost": cost}


MAX_ORDER_QUESTIONS = 40
MAX_SUGGESTIONS = 4
QUESTION_MAX = 500


_STOPWORDS = {"a", "an", "the", "is", "are", "was", "were", "be", "do", "does",
              "did", "have", "has", "had", "what", "why", "how", "when", "where",
              "which", "of", "to", "in", "on", "at", "for", "with", "it", "its",
              "that", "this", "these", "those", "and", "or", "but", "if", "so",
              "i", "my", "me", "you", "your", "we", "our", "s"}

# how much two questions must overlap to count as the same one. Exact key
# equality is too brittle — "why do B-trees have high fanout?" and "why is the
# fanout of B-trees high?" differ by one filler word and are plainly the same
# question — while a lower bar would swallow genuinely different ones ("what
# is a B-tree?" vs "what is a B-tree node?" sits at 0.67 and must survive).
SAME_QUESTION_OVERLAP = 0.7


def _question_words(text: str) -> frozenset:
    """The content words of a question: case, punctuation, word order, and
    grammatical filler all discarded."""
    return frozenset(w for w in re.findall(r"[a-z0-9]+", text.lower())
                     if w not in _STOPWORDS)


def _same_question(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return a == b
    return len(a & b) / len(a | b) >= SAME_QUESTION_OVERLAP


def handle_suggest_questions(body: dict, call_model) -> dict:
    """A few questions the global bank implies but nobody wrote down.

    Suggestions only — nothing is added anywhere by this call. The caller
    shows them and the reader keeps or discards each one, so the handler's
    job is just to return a short, clean, non-duplicate list.
    """
    raw = body.get("questions")
    if not isinstance(raw, list):
        raise ApiError("missing 'questions'")
    existing = [str(q or "").strip()[:QUESTION_MAX] for q in raw[:MAX_ORDER_QUESTIONS]]
    existing = [q for q in existing if q]
    if not existing:
        raise ApiError("no questions to suggest from")

    text, cost = call_model(
        SUGGEST_QUESTIONS_SYSTEM,
        [{"role": "user", "content": suggest_questions_message(existing, MAX_SUGGESTIONS)}],
        "glossary", effort="none", max_tokens=600,
    )
    data = first_json_object(text)
    proposed = data.get("questions") if isinstance(data, dict) else None

    seen = [_question_words(q) for q in existing]
    out = []
    for q in proposed if isinstance(proposed, list) else []:
        q = " ".join(str(q or "").split())[:QUESTION_MAX]
        words = _question_words(q)
        # too short to be a question, or one they already have in other words
        # (including one an earlier suggestion in this same batch already made)
        if len(q) < 8 or not words or any(_same_question(words, s) for s in seen):
            continue
        seen.append(words)
        out.append(q)
        if len(out) >= MAX_SUGGESTIONS:
            break
    return {"questions": out, "cost": cost}


def handle_order_questions(body: dict, call_model) -> dict:
    """Sort a bank of questions into dependency order, on the cheap model.

    Returns the permutation as indices into the list that was sent, so the
    caller doesn't have to trust the model with ids or text round-tripping.
    Anything the model leaves out, repeats, or invents is repaired here: the
    result is always every index exactly once, in the model's order where it
    made sense and the original order for the rest. Worst case (an unusable
    reply) that repair yields the input order, so the button can never lose
    or duplicate a question.
    """
    raw = body.get("questions")
    if not isinstance(raw, list):
        raise ApiError("missing 'questions'")
    questions = [str(q or "").strip()[:500] for q in raw[:MAX_ORDER_QUESTIONS]]
    questions = [q for q in questions if q]
    if len(questions) < 2:
        return {"order": list(range(len(questions))), "cost": 0.0}

    text, cost = call_model(
        ORDER_QUESTIONS_SYSTEM,
        [{"role": "user", "content": order_questions_message(questions)}],
        "glossary", effort="none", max_tokens=600,
    )
    data = first_json_object(text)
    proposed = data.get("order") if isinstance(data, dict) else None

    order, seen = [], set()
    for i in proposed if isinstance(proposed, list) else []:
        if isinstance(i, bool):          # bool is an int in python; not an index
            continue
        if isinstance(i, str) and i.strip().lstrip("-").isdigit():
            i = int(i)
        if isinstance(i, int) and 0 <= i < len(questions) and i not in seen:
            seen.add(i)
            order.append(i)
    order += [i for i in range(len(questions)) if i not in seen]   # never drop one
    return {"order": order, "cost": cost}


def handle_quiz(body: dict, call_model) -> dict:
    """3-8 multiple-choice questions built from the tree's conversations —
    retrieval practice on what the learner actually covered."""
    recap = (body.get("recap") or "").strip()
    if not recap:
        raise ApiError("missing 'recap'")
    try:
        count = max(3, min(8, int(body.get("count") or 5)))
    except (TypeError, ValueError):
        count = 5
    message = quiz_message((body.get("root_topic") or "").strip()[:200], recap[:24000], count)
    text, cost = call_model(QUIZ_SYSTEM, [{"role": "user", "content": message}], "tutor")
    data = first_json_object(text)
    questions = []
    for q in (data.get("questions") if isinstance(data, dict) else None) or []:
        if not isinstance(q, dict):
            continue
        choices = [str(c).strip() for c in (q.get("choices") or []) if str(c).strip()]
        answer = q.get("answer")
        if (
            str(q.get("q") or "").strip()
            and len(choices) == 4
            and isinstance(answer, int)
            and 0 <= answer < 4
        ):
            questions.append({
                "q": str(q["q"]).strip(),
                "choices": choices,
                "answer": answer,
                "why": str(q.get("why") or "").strip(),
            })
    if not questions:
        raise ApiError("the model returned no usable questions — try again", 502)
    return {"questions": questions, "cost": cost}


# --------------------------------------------------------------------------- #
# the written exam: one route writes the paper, one marks the script. Both run
# on the "examiner" role so a backend can point them at a stronger model than
# the conversation itself uses — setting a fair paper and marking essays are
# the two judgement calls in this app that most reward one.
# --------------------------------------------------------------------------- #
EXAM_MATERIAL_MAX = 40000   # the tutorial transcript, in full — see handle_exam
EXAM_MIN_Q, EXAM_MAX_Q, EXAM_DEFAULT_Q = 3, 8, 5
EXAM_MARKS = 10             # per question, fixed — the client says so on screen
EXAM_ANSWER_MAX = 6000      # one essay answer
EXAM_Q_MAX = 700


def exam_count(raw) -> int:
    try:
        return max(EXAM_MIN_Q, min(EXAM_MAX_Q, int(raw or EXAM_DEFAULT_Q)))
    except (TypeError, ValueError):
        return EXAM_DEFAULT_Q


def _exam_material(body: dict) -> str:
    """The conversation being examined, untruncated.

    Deliberately NOT conversation_digest(): that clips every tutor answer to
    240 characters, which is fine for reminding a learner what was covered and
    useless as a syllabus. Both setting a fair paper and marking against it
    need the actual substance — a question the material never supported, or a
    correct answer marked wrong because the marker never saw the sentence that
    licensed it, are both failures of this one input.
    """
    material = (body.get("material") or "").strip()
    if not material:
        raise ApiError("missing 'material'")
    return material[:EXAM_MATERIAL_MAX]


def _str_list(raw, limit: int, cap: int) -> list:
    return [" ".join(str(x or "").split())[:cap]
            for x in (raw if isinstance(raw, list) else [])
            if str(x or "").strip()][:limit]


def handle_exam(body: dict, call_model) -> dict:
    """Set a written paper on one conversation: essay questions with the mark
    scheme each will be marked against."""
    material = _exam_material(body)
    count = exam_count(body.get("count"))
    message = exam_message(
        (body.get("root_topic") or "").strip()[:200],
        (body.get("label") or "").strip()[:200],
        material,
        count,
    )
    text, cost = call_model(EXAM_SYSTEM, [{"role": "user", "content": message}], "examiner")
    data = first_json_object(text)
    questions = []
    for q in (data.get("questions") if isinstance(data, dict) else None) or []:
        if not isinstance(q, dict):
            continue
        stem = " ".join(str(q.get("q") or "").split())[:EXAM_Q_MAX]
        if len(stem) < 10:
            continue
        kind = str(q.get("kind") or "").strip().lower()
        questions.append({
            "q": stem,
            "kind": kind if kind in EXAM_KINDS else "",
            "command": " ".join(str(q.get("command") or "").split())[:40].lower(),
            "marks": EXAM_MARKS,
            "points": _str_list(q.get("points"), 6, 300),
            "terms": _str_list(q.get("terms"), 8, 60),
        })
        if len(questions) >= count:
            break
    if not questions:
        raise ApiError("the examiner returned no usable questions — try again", 502)
    return {"questions": questions, "cost": cost}


def handle_mark_exam(body: dict, call_model) -> dict:
    """Mark a whole script in one call, against the scheme the paper was set
    with. Marks are clamped and totalled here rather than trusted from the
    model, so the arithmetic on screen is always right even when the prose
    around it is generous."""
    material = _exam_material(body)
    raw = body.get("answers")
    questions = body.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ApiError("missing 'questions'")
    answers = raw if isinstance(raw, list) else []
    script = []
    for i, q in enumerate(questions[:EXAM_MAX_Q]):
        if not isinstance(q, dict):
            continue
        stem = " ".join(str(q.get("q") or "").split())[:EXAM_Q_MAX]
        if not stem:
            continue
        written = answers[i] if i < len(answers) else ""
        script.append({
            "q": stem,
            "points": _str_list(q.get("points"), 6, 300),
            "terms": _str_list(q.get("terms"), 8, 60),
            "answer": (written if isinstance(written, str) else "")[:EXAM_ANSWER_MAX],
        })
    if not script:
        raise ApiError("nothing to mark")
    if not any(item["answer"].strip() for item in script):
        raise ApiError("every answer is blank — write something first")

    message = mark_exam_message(
        (body.get("root_topic") or "").strip()[:200],
        (body.get("label") or "").strip()[:200],
        material,
        script,
    )
    text, cost = call_model(
        MARK_EXAM_SYSTEM, [{"role": "user", "content": message}], "examiner",
    )
    data = first_json_object(text)
    raw_results = (data.get("results") if isinstance(data, dict) else None) or []
    results = []
    for i, item in enumerate(script):
        r = raw_results[i] if i < len(raw_results) and isinstance(raw_results[i], dict) else {}
        try:
            marks = int(round(float(r.get("marks"))))
        except (TypeError, ValueError):
            marks = 0
        earned = space_sentences(str(r.get("earned") or "").strip())[:2500]
        improve = space_sentences(str(r.get("improve") or "").strip())[:2500]
        results.append({
            "marks": max(0, min(EXAM_MARKS, marks)),
            "earned": earned,
            "improve": improve,
            "hit": _str_list(r.get("hit"), 6, 300),
            "missed": _str_list(r.get("missed"), 6, 300),
        })
    if not any(r["earned"] or r["improve"] for r in results):
        raise ApiError("the examiner returned no usable feedback — try again", 502)
    overall = space_sentences(
        str((data.get("overall") if isinstance(data, dict) else "") or "").strip()
    )[:2000]
    return {
        "results": results,
        "overall": overall,
        "total": sum(r["marks"] for r in results),
        "max": len(results) * EXAM_MARKS,
        "cost": cost,
    }


# --------------------------------------------------------------------------- #
# 🖼 illustrate — a picture of one highlighted passage, in two stages.
#
# Stage one is a text model writing the brief (see ILLUSTRATE_SYSTEM: what has
# a shape here, and what would drawing it teach). Stage two is Gemini drawing
# it. The split is the whole design: it is what lets the app decline to draw
# an idea that has no shape, and what produces the alt text and caption — a
# picture with no alt text would be a step backwards for a reader who needs
# this app's screen-reader path.
#
# The bytes come straight back to the browser rather than being filed here.
# This handler stays stateless like every other route; the client re-encodes
# the image small and PUTs it to the byte store (api/images.js hosted,
# localweb's ImageStore locally), because a knowledge tree caps at 2 MB and a
# PNG would eat it whole.
# --------------------------------------------------------------------------- #
ILLUSTRATE_PASSAGE_MAX = 600
ILLUSTRATE_LABELS_MAX = 6
ILLUSTRATE_ELEMENTS_MAX = 6


def _unique(items: list, limit: int) -> list:
    """Order-preserving, case-insensitive dedupe."""
    seen, out = set(), []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _illustrate_brief(data) -> dict:
    """Stage one's reply, clamped to what build_prompt() will actually use.

    Every cap here is a quality guard rather than a safety one: a brief with
    twelve labels produces a figure with twelve chances to render a misspelt
    word, and a 400-character "layout" produces a model that ignores all of it.
    """
    if not isinstance(data, dict):
        raise ApiError("the art director returned nothing usable — try again", 502)
    if data.get("drawable") is False:
        why = " ".join(str(data.get("why") or "").split())[:300]
        return {"drawable": False,
                "why": why or "there isn't a shape in this passage worth drawing"}

    subject = " ".join(str(data.get("subject") or "").split())[:400]
    if not subject:
        raise ApiError("the art director returned nothing usable — try again", 502)
    kind = str(data.get("kind") or "").strip().lower()
    if kind not in gemini_images.KINDS:
        kind = gemini_images.DEFAULT_KIND
    caption = " ".join(str(data.get("caption") or "").split())[:80] or subject[:80]
    alt = " ".join(str(data.get("alt") or "").split())[:400] or caption
    return {
        "drawable": True,
        "subject": subject,
        "kind": kind,
        "elements": _str_list(data.get("elements"), ILLUSTRATE_ELEMENTS_MAX, 200),
        "layout": " ".join(str(data.get("layout") or "").split())[:300],
        # 1-3 words each: the whitelist is only protective while it is short.
        # Deduped because a repeat is an instruction to write the same word
        # twice on the figure, which is exactly the clutter it exists to stop.
        "labels": _unique(_str_list(data.get("labels"), ILLUSTRATE_LABELS_MAX * 2, 40),
                          ILLUSTRATE_LABELS_MAX),
        "avoid": " ".join(str(data.get("avoid") or "").split())[:200],
        "caption": caption,
        "alt": alt,
    }


def handle_illustrate(body: dict, call_model) -> dict:
    passage = " ".join(str(body.get("passage") or "").split())[:ILLUSTRATE_PASSAGE_MAX]
    if len(passage) < 2:
        raise ApiError("missing 'passage'")
    if not gemini_images.available():
        raise ApiError(
            "image generation is off — GEMINI_API_KEY is not set on the server",
            503,
        )

    message = illustrate_message(
        passage,
        (body.get("topic") or "").strip()[:200],
        (body.get("label") or "").strip()[:120],
        (body.get("context") or "").strip()[:4000],
        " ".join(str(body.get("hint") or "").split())[:300],
    )
    # a short, structured answer: xhigh effort would only make it slower and
    # dearer, and the judgement it needs is "does this have a shape", not depth
    text, brief_cost = call_model(
        ILLUSTRATE_SYSTEM, [{"role": "user", "content": message}], "tutor",
        effort="low", max_tokens=1200,
    )
    brief = _illustrate_brief(first_json_object(text))
    if not brief["drawable"]:
        # not an error: declining to draw an idea with no shape is the feature
        # working. 200 so the client can say it gently instead of going red.
        return {"drawable": False, "why": brief["why"], "cost": brief_cost}

    prompt = gemini_images.build_prompt(brief)
    aspect = gemini_images.clean_aspect(body.get("aspect"), brief["kind"])
    try:
        b64, mime, image_cost = gemini_images.generate(prompt, aspect)
    except gemini_images.ImageError as exc:
        raise ApiError(str(exc), exc.status) from exc

    return {
        "drawable": True,
        "data": b64,
        "mime": mime,
        "alt": brief["alt"],
        "caption": brief["caption"],
        "kind": brief["kind"],
        "labels": brief["labels"],
        "aspect": aspect,
        # what the tutor is shown when you ask a question about the figure:
        # the brief it was drawn from, which is a truer account of the picture
        # than any caption, and costs nothing to carry
        "brief": brief["subject"],
        "cost": brief_cost + image_cost,
        "image_cost": image_cost,
    }


# --------------------------------------------------------------------------- #
# ⚡ fact me out — one call, a whole factual landscape (see FACTS_SYSTEM).
# --------------------------------------------------------------------------- #
FACTS_MAX_GROUPS = 10
FACTS_MAX_PER_GROUP = 12
FACTS_MAX_TOTAL = 90
FACT_TEXT_MAX = 300

# Deliberately lower than SAME_QUESTION_OVERLAP. That bar is set where it is
# because two short questions can differ by one content word and mean genuinely
# different things ("what is a B-tree?" / "what is a B-tree node?" sit at 0.67
# and must both survive). A fact is a whole sentence carrying 12-20 content
# words, so that near-miss doesn't arise: at this length, sharing three words
# in five means it is the same fact reworded, which is exactly the padding
# this list must not contain.
SAME_FACT_OVERLAP = 0.6


def _same_fact(a: frozenset, b: frozenset) -> bool:
    if not a or not b:
        return a == b
    return len(a & b) / len(a | b) >= SAME_FACT_OVERLAP


def handle_facts(body: dict, call_model) -> dict:
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise ApiError("missing 'topic'")
    message = facts_message(topic[:200], (body.get("angle") or "").strip()[:120])
    # A knowledge-bound task, not a reasoning-bound one: the model is
    # recalling and *selecting*, not working anything out, and this is one
    # call producing a lot of output. Full effort would multiply the wait
    # without improving which facts get picked.
    text, cost = call_model(
        FACTS_SYSTEM, [{"role": "user", "content": message}], "facts",
        effort="medium",
    )
    data = first_json_object(text)

    groups, total, seen = [], 0, set()
    for g in (data.get("groups") if isinstance(data, dict) else None) or []:
        if not isinstance(g, dict):
            continue
        name = " ".join(str(g.get("name") or "").split())[:80]
        if not name:
            continue
        facts = []
        for f in (g.get("facts") if isinstance(g.get("facts"), list) else [])[
                :FACTS_MAX_PER_GROUP]:
            if isinstance(f, str):
                f = {"text": f}
            if not isinstance(f, dict):
                continue
            fact = " ".join(str(f.get("text") or "").split())[:FACT_TEXT_MAX]
            # a "fact" of four words is a heading that lost its way
            if len(fact) < 12:
                continue
            # the prompt forbids repetition; this catches it happening anyway,
            # since the same fact under two headings reads as padding
            key = _question_words(fact)
            if any(_same_fact(key, s) for s in seen):
                continue
            seen.add(key)
            kind = str(f.get("kind") or "").strip().lower()
            facts.append({"text": fact,
                          "kind": kind if kind in FACT_KINDS else ""})
            total += 1
            if total >= FACTS_MAX_TOTAL:
                break
        if facts:
            groups.append({"name": name, "facts": facts})
        if len(groups) >= FACTS_MAX_GROUPS or total >= FACTS_MAX_TOTAL:
            break

    if not groups:
        raise ApiError("the model returned no usable facts — try again", 502)
    return {"groups": groups, "count": total, "cost": cost}


def _survey_items(raw, depth: int) -> list:
    """Validate/clip a survey breakdown: [{name, why, items?}] at most
    `depth` levels deep, at most 6 items per level."""
    items = []
    for it in (raw if isinstance(raw, list) else [])[:6]:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:80]
        if not name:
            continue
        entry = {"name": name, "why": str(it.get("why") or "").strip()[:300]}
        if depth > 1:
            subs = _survey_items(it.get("items"), depth - 1)
            if subs:
                entry["items"] = subs
        items.append(entry)
    return items


def handle_survey(body: dict, call_model) -> dict:
    """Map a broad topic: the foundational components it is built upon, two
    levels deep. `focus` re-runs the breakdown on one component of the map;
    `existing` lists names already mapped so the model doesn't repeat them."""
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise ApiError("missing 'topic'")
    focus = (body.get("focus") or "").strip()[:120]
    existing = [str(x).strip()[:80] for x in (body.get("existing") or [])
                if str(x).strip()][:80]
    message = survey_message(topic[:200], focus, existing)
    text, cost = call_model(SURVEY_SYSTEM, [{"role": "user", "content": message}], "tutor")
    data = first_json_object(text)
    items = _survey_items(data.get("items") if isinstance(data, dict) else None, 2)
    if not items:
        raise ApiError("the model returned no usable breakdown — try again", 502)
    return {"items": items, "cost": cost}


def handle_export_md(body: dict) -> dict:
    tree = body.get("tree")
    if not isinstance(tree, dict):
        raise ApiError("missing 'tree'")
    kb = KnowledgeTree.from_dict(tree)
    return {"markdown": kb.to_markdown(), "filename": kb.default_filename().replace(".know.json", ".md")}


def handle_export_html(body: dict) -> dict:
    tree = body.get("tree")
    if not isinstance(tree, dict):
        raise ApiError("missing 'tree'")
    from .export_html import tree_to_html

    kb = KnowledgeTree.from_dict(tree)
    return {"html": tree_to_html(kb), "filename": kb.default_filename().replace(".know.json", ".html")}


def handle_digest(body: dict) -> dict:
    """Server-side conversation_digest so the recap text matches the CLI."""
    return {"digest": conversation_digest(body.get("turns", []), body.get("upto"))}


def model_routes(call_model, tutor_grounding=None, learner_grounding=None) -> dict:
    """The POST route table every backend serves, bound to its transport.

    Both grounding hooks are local-mode-only, and both are evaluated fresh per
    request since local settings (and the anchored session itself) can change
    while the server runs. api/index.py (hosted) passes neither, so its tutor
    gets grounding=None and its learner gets no brief — behaviour there is
    exactly as it was before either existed.

    `tutor_grounding`: a string, a zero-arg callable returning one, or None.
    `learner_grounding`: a zero-arg callable returning (brief, cost). It costs
    something because the brief is generated, not read, so the cost rides back
    with the learner turn that triggered it.
    """
    def _grounding() -> "str | None":
        return tutor_grounding() if callable(tutor_grounding) else tutor_grounding

    def _brief() -> tuple:
        if not callable(learner_grounding):
            return "", 0.0
        got = learner_grounding()
        return got if isinstance(got, tuple) else (got or "", 0.0)

    return {
        "learner": lambda body: handle_learner(body, call_model, *_brief()),
        "tutor": lambda body: handle_tutor(body, call_model, grounding=_grounding()),
        "next_concept": lambda body: handle_next_concept(body, call_model),
        "interview": lambda body: handle_interview(body, call_model),
        "teachback": lambda body: handle_teachback(body, call_model),
        "define": lambda body: handle_define(body, call_model),
        "quiz": lambda body: handle_quiz(body, call_model),
        "facts": lambda body: handle_facts(body, call_model),
        "illustrate": lambda body: handle_illustrate(body, call_model),
        "exam": lambda body: handle_exam(body, call_model),
        "mark_exam": lambda body: handle_mark_exam(body, call_model),
        "order_questions": lambda body: handle_order_questions(body, call_model),
        "suggest_questions": lambda body: handle_suggest_questions(body, call_model),
        "survey": lambda body: handle_survey(body, call_model),
        "export_md": handle_export_md,
        "export_html": handle_export_html,
        "digest": handle_digest,
    }
