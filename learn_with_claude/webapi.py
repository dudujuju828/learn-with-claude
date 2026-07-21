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

from .knowledge import KnowledgeTree, conversation_digest
from .personas import (
    GLOSSARY_SYSTEM,
    INTERVIEW_FINISH,
    INTERVIEW_SYSTEM,
    LEARNER_LEVELS,
    NEXT_CONCEPT_SYSTEM,
    QUIZ_SYSTEM,
    SURVEY_SYSTEM,
    TEACHBACK_SYSTEM,
    TUTOR_MODES,
    branch_learner_message,
    branch_tutor_context,
    define_message,
    feedback_message,
    first_learner_message,
    followup_learner_message,
    followup_tutor_context,
    gaps_learner_message,
    gaps_tutor_context,
    interview_budget_note,
    interview_opening,
    learner_system,
    next_concept_message,
    quiz_message,
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
def learner_opening(body: dict) -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        return branch_learner_message(
            body["topic"], body.get("breadcrumb", ""), body.get("digest", ""),
            body.get("branch_q", ""), body.get("branch_a", ""), body.get("focus", ""),
        )
    if kind == "followup":
        return followup_learner_message(
            body["topic"], body.get("recap", ""),
            body.get("concept", ""), body.get("opening_question", ""),
        )
    if kind == "gaps":
        return gaps_learner_message(
            body["topic"], body.get("baseline", ""),
            body.get("focus", ""), body.get("opening_question", ""),
        )
    return first_learner_message(body["topic"])


def tutor_extra_context(body: dict) -> str:
    kind = body.get("kind", "root")
    if kind == "branch":
        return branch_tutor_context(body.get("digest", ""), body.get("branch_a", ""))
    if kind == "followup":
        return followup_tutor_context(body.get("recap", ""), body.get("concept", ""))
    if kind == "gaps":
        return gaps_tutor_context(body.get("baseline", ""))
    return ""


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


def handle_learner(body: dict, call_model) -> dict:
    level = body.get("level")
    if level not in LEARNER_LEVELS:
        level = "student"
    messages = [{"role": "user", "content": learner_opening(body)}]
    for t in body.get("turns", []):
        messages.append({"role": "assistant", "content": turn_json(t)})
        messages.append({"role": "user", "content": feedback_message(t.get("tutor", ""))})
    text, cost = call_model(learner_system(level), messages, "learner")
    data = extract_turn(text)
    return {
        "thinking": (data.get("thinking") or "").strip(),
        "new_term": clean_term(data.get("new_term")),
        "action": (data.get("action") or "").strip(),
        "confidence": data.get("confidence"),
        "done": bool(data.get("done")),
        "cost": cost,
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


def handle_tutor(body: dict, call_model) -> dict:
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
    system = tutor_system(diagrams=False, mode=mode, custom_style=custom, segments=True)
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
    and one probing question. Feedback, not a grade — content only."""
    explanation = (body.get("explanation") or "").strip()
    if not explanation:
        raise ApiError("missing 'explanation'")
    message = teachback_message(
        (body.get("topic") or "").strip()[:200],
        (body.get("label") or "").strip()[:120],
        (body.get("digest") or "").strip()[:24000],
        explanation[:8000],
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
    """One glossary definition, on the cheap model. Context is the exchange
    where the learner hit the term, so the definition matches its use there."""
    term = (body.get("term") or "").strip()
    if not term:
        raise ApiError("missing 'term'")
    message = define_message(
        term[:120],
        (body.get("topic") or "").strip()[:200],
        (body.get("context") or "").strip()[:4000],
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


def model_routes(call_model) -> dict:
    """The POST route table every backend serves, bound to its transport."""
    return {
        "learner": lambda body: handle_learner(body, call_model),
        "tutor": lambda body: handle_tutor(body, call_model),
        "next_concept": lambda body: handle_next_concept(body, call_model),
        "interview": lambda body: handle_interview(body, call_model),
        "teachback": lambda body: handle_teachback(body, call_model),
        "define": lambda body: handle_define(body, call_model),
        "quiz": lambda body: handle_quiz(body, call_model),
        "survey": lambda body: handle_survey(body, call_model),
        "export_md": handle_export_md,
        "export_html": handle_export_html,
        "digest": handle_digest,
    }
