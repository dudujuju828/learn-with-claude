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

from .backend import ClaudeSession
from .diagrams import DIAGRAM_TOOL, excalidraw_mcp_config
from .personas import (
    LEARNER_SYSTEM,
    NEXT_CONCEPT_SYSTEM,
    feedback_message,
    first_learner_message,
    next_concept_message,
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
    tutor_extra_system: str = "",
    max_turns: int = 20,
    learner_model: str = "claude-sonnet-5",
    tutor_model: str = "claude-sonnet-5",
    effort: str = "xhigh",
    vault: str | None = None,
    timeout: int = 300,
    renderer: Renderer | None = None,
) -> ConversationResult:
    r = renderer or Renderer(color=True)

    learner = ClaudeSession(
        system_prompt=LEARNER_SYSTEM,
        model=learner_model,
        effort=effort,
        exclude_dynamic=True,
        timeout=timeout,
    )
    mcp_config = excalidraw_mcp_config(vault) if vault else None
    tutor_prompt = tutor_system(diagrams=mcp_config is not None)
    if tutor_extra_system:
        tutor_prompt += f"\n\n{tutor_extra_system}"
    tutor = ClaudeSession(
        system_prompt=tutor_prompt,
        model=tutor_model,
        effort=effort,
        exclude_dynamic=True,
        timeout=timeout,
        mcp_config=mcp_config,
        allowed_tools=[DIAGRAM_TOOL] if mcp_config else None,
    )

    result = ConversationResult()
    message = learner_first_msg or first_learner_message(topic)

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
        tutor_text = space_sentences(tutor_reply.text)
        r.tutor(tutor_text)

        record["tutor"] = tutor_text
        result.turns.append(record)
        if confidence is not None:
            result.final_confidence = confidence

        if done:
            break
        message = feedback_message(tutor_text)

    result.cost = learner.total_cost + tutor.total_cost
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
