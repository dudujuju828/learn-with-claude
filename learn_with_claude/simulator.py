"""The reusable learner<->tutor conversation loop.

`run_conversation` powers both a fresh root investigation and a re-investigation
branch (which simply passes a different opening message for the learner and some
extra context for the tutor). It returns structured turns + cost; persistence is
handled by the knowledge tree, not here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .backend import ClaudeError, ClaudeSession
from .personas import (
    LEARNER_SYSTEM,  # noqa: F401 - kept for older callers
    NEXT_CONCEPT_SYSTEM,
    feedback_message,
    first_learner_message,
    learner_system,
    next_concept_message,
    review_message,
    review_system,
    tutor_system,
)
from .render import Renderer, space_sentences


# --------------------------------------------------------------------------- #
# Parsing the learner's structured turn
# --------------------------------------------------------------------------- #
def first_json_object(text: str) -> "dict | None":
    """Extract the first balanced JSON object from a reply, tolerating code
    fences or stray prose around it. Returns None if nothing parses."""
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s).strip()

    start = s.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(s[start : i + 1])
                    except json.JSONDecodeError:
                        return None
    return None


def extract_turn(text: str) -> dict:
    """Pull the learner's {thinking, new_term, action, confidence, done} object
    out of its reply."""
    obj = first_json_object(text)
    if isinstance(obj, dict):
        obj.setdefault("thinking", "")
        obj.setdefault("new_term", None)
        obj.setdefault("action", "")
        obj.setdefault("confidence", None)
        obj.setdefault("done", False)
        return obj

    # Fallback: treat the whole reply as the action so the loop keeps going.
    return {
        "thinking": "",
        "new_term": None,
        "action": text.strip(),
        "confidence": None,
        "done": False,
        "_unparsed": True,
    }


def clean_term(value) -> str:
    """Normalise the learner's new_term: treat null/none/empty as no term."""
    if not isinstance(value, str):
        return ""
    v = value.strip()
    return "" if v.lower() in ("", "null", "none", "n/a") else v


# --------------------------------------------------------------------------- #
# Parsing the reviewer's verdict (🔍 double-check — see REVIEW_JOB in
# personas.py). Every clamp here exists to stop the cure being worse than the
# disease: a checker that rewrites for taste, or quietly pads an answer past
# the length the reader asked for, has damaged the thing it was hired to
# protect. It lives beside extract_turn() because it is the same job — pull a
# structure you can trust out of a reply you can't — and because both web
# backends and the CLI need it, which rules out putting it in either.
# --------------------------------------------------------------------------- #
REVIEW_ISSUES_MAX = 6
REVIEW_NOTE_MAX = 240
# A repair is a repair, not a second draft. Correcting a claim or cutting an
# unsupported one shortens prose far more often than it lengthens it, so a
# reply that came back much longer is a reviewer that has answered the question
# again in its own words — the tutor's brief broken by the party enforcing it.
# The floor keeps very short answers, where one added clause is legitimately a
# big relative jump, from tripping it.
REVIEW_GROWTH = 1.8
REVIEW_GROWTH_FLOOR = 400


def review_result(data, original: str) -> tuple:
    """The reviewer's reply, clamped. Returns (text_to_show, checked_or_None).

    `checked` is what gets stored on the turn: ``{"issues": []}`` for a clean
    read, ``{"issues": [...], "before": ...}`` for a repair, and ``None`` when
    the review produced nothing trustworthy — in which case the original
    stands and the turn carries no mark at all, because claiming a check that
    didn't really happen is the one outcome worse than not checking.
    """
    from .personas import REVIEW_KINDS

    if not isinstance(data, dict):
        return original, None
    verdict = str(data.get("verdict") or "").strip().lower()

    issues = []
    raw = data.get("issues")
    for item in (raw if isinstance(raw, list) else [])[:REVIEW_ISSUES_MAX]:
        if isinstance(item, str):
            item = {"note": item}
        if not isinstance(item, dict):
            continue
        note = " ".join(str(item.get("note") or "").split())[:REVIEW_NOTE_MAX]
        if not note:
            continue
        kind = str(item.get("kind") or "").strip().lower()
        issues.append({"kind": kind if kind in REVIEW_KINDS else "", "note": note})

    revised = str(data.get("answer") or "").strip()
    if revised and revised != original.strip() and verdict != "clean":
        # a rewrite with no stated reason is a rewrite nobody can check —
        # exactly the position this whole feature exists to get the reader out
        # of, so it is refused rather than shown
        if not issues:
            return original, None
        if len(revised) > max(REVIEW_GROWTH_FLOOR, int(len(original) * REVIEW_GROWTH)):
            return original, None
        return revised, {"issues": issues, "before": original}
    # Not a repair. Only a reply that actually SAID so earns the read-and-sound
    # mark: any issues claimed beside untouched text would be a badge pointing
    # at nothing, and an unparseable reply that fell through to here never
    # checked anything at all.
    if verdict == "clean" or (verdict == "revise" and revised):
        return original, {"issues": []}
    return original, None


# --------------------------------------------------------------------------- #
# Result container
# --------------------------------------------------------------------------- #
@dataclass
class ConversationResult:
    turns: list = field(default_factory=list)  # {turn, thinking, new_term, action, confidence, done, tutor}
    cost: float = 0.0
    final_confidence: object = None


# --------------------------------------------------------------------------- #
# The loop
# --------------------------------------------------------------------------- #
def run_conversation(
    topic: str,
    *,
    learner_first_msg: str | None = None,
    anchor: str | None = None,
    tutor_extra_system: str = "",
    max_turns: int = 20,
    learner_model: str = "claude-sonnet-5",
    tutor_model: str = "claude-sonnet-5",
    effort: str = "xhigh",
    level: str = "student",
    timeout: int = 300,
    double_check: bool = False,
    renderer: Renderer | None = None,
) -> ConversationResult:
    """Run one investigation: learner and tutor alternating until done.

    `anchor` is the question this investigation exists to answer, restated to
    the learner every turn so it doesn't drift off into whatever the tutor's
    last reply happened to mention. It defaults to `topic`, which is right
    whenever `topic` IS the question being investigated — callers that pass a
    `learner_first_msg` framing a different question (a branch, say) should
    pass the matching anchor too.

    `double_check` (🔍) sends each tutor reply to a reviewer before it is
    printed or recorded. It costs a third model call per turn.
    """
    r = renderer or Renderer(color=True)

    learner = ClaudeSession(
        system_prompt=learner_system(level),
        model=learner_model,
        effort=effort,
        exclude_dynamic=True,
        timeout=timeout,
    )
    tutor_prompt = tutor_system()
    if tutor_extra_system:
        tutor_prompt += f"\n\n{tutor_extra_system}"
    tutor = ClaudeSession(
        system_prompt=tutor_prompt,
        model=tutor_model,
        effort=effort,
        exclude_dynamic=True,
        timeout=timeout,
    )

    result = ConversationResult()
    message = learner_first_msg or first_learner_message(topic)
    # 🔍 the reviewer gets a FRESH session per reply rather than one running
    # conversation: it is reading finished prose cold, and a reviewer that
    # remembers waving the last four answers through is no longer reading this
    # one. Cost is summed across them by hand for the same reason.
    review_cost = 0.0

    def double_checked(question: str, answer: str) -> tuple:
        nonlocal review_cost
        session = ClaudeSession(
            system_prompt=review_system(),
            model=tutor_model,
            effort=effort,
            exclude_dynamic=True,
            timeout=timeout,
        )
        r.status("double-checking that answer…")
        try:
            reply = session.send(review_message(question, answer))
        except ClaudeError as exc:
            # the answer is written and already paid for; a checker that fell
            # over must not take it away
            r.clear_status()
            r.warn(f"double-check skipped: {exc}")
            return answer, None
        finally:
            review_cost += session.total_cost
        r.clear_status()
        return review_result(first_json_object(reply.text), answer)

    for turn in range(1, max_turns + 1):
        r.status(f"turn {turn}: learner is thinking…")
        learner_reply = learner.send(message)
        data = extract_turn(learner_reply.text)
        r.clear_status()

        thinking = (data.get("thinking") or "").strip()
        new_term = clean_term(data.get("new_term"))
        action = (data.get("action") or "").strip()
        confidence = data.get("confidence")
        done = bool(data.get("done"))

        r.learner(turn, thinking, new_term, action, confidence)

        record = {
            "turn": turn,
            "thinking": thinking,
            "new_term": new_term,
            "action": action,
            "confidence": confidence,
            "done": done,
            "tutor": "",
        }

        if not action:
            result.turns.append(record)
            break

        r.status(f"turn {turn}: claude is answering…")
        tutor_reply = tutor.send(action)
        r.clear_status()
        tutor_text = tutor_reply.text
        checked = None
        if double_check:
            tutor_text, checked = double_checked(action, tutor_text)
        tutor_text = space_sentences(tutor_text)
        r.tutor(tutor_text)
        if checked:
            r.checked(checked.get("issues") or [])

        record["tutor"] = tutor_text
        if checked is not None:
            if "before" in checked:
                checked["before"] = space_sentences(checked["before"])
            record["checked"] = checked
        result.turns.append(record)
        if confidence is not None:
            result.final_confidence = confidence

        if done:
            break
        message = feedback_message(tutor_text, anchor or topic)

    result.cost = learner.total_cost + tutor.total_cost + review_cost
    return result


# --------------------------------------------------------------------------- #
# Choosing the next concept (for `full` sessions)
# --------------------------------------------------------------------------- #
def pick_next_concept(
    root_topic: str,
    covered: list,
    recap: str,
    *,
    model: str = "claude-sonnet-5",
    effort: str = "xhigh",
    timeout: int = 300,
) -> "tuple[dict | None, float]":
    """One-shot tutor call: review the session recap and choose the next
    related concept worth exploring. Returns (pick, cost) where pick is
    {"concept", "opening_question", "reason"} or None if unparseable."""
    session = ClaudeSession(
        system_prompt=NEXT_CONCEPT_SYSTEM,
        model=model,
        effort=effort,
        exclude_dynamic=True,
        timeout=timeout,
    )
    reply = session.send(next_concept_message(root_topic, covered, recap))
    pick = first_json_object(reply.text)
    if not isinstance(pick, dict) or not str(pick.get("concept") or "").strip():
        return None, session.total_cost
    return pick, session.total_cost
