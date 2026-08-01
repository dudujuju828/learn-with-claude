"""Gemini as an image transport — the one thing in this app that isn't Claude.

Stdlib only (urllib), like the rest of the package, so the *same* module serves
both web backends: the Vercel function and the localhost Copilot server both
run Python and both read GEMINI_API_KEY. Nothing here knows about trees,
routes, or HTTP shapes — see webapi.handle_illustrate for the two-stage flow
this is the second half of.

The prompt builder is the important part of this file. An image model handed a
paragraph of tutor prose draws something confidently irrelevant, with labels
in a language that doesn't exist. What actually works is a *brief*: one
subject, an explicit spatial layout, a short whitelist of labels spelled out,
and a flat-vector style that forbids the photoreal mush a bare prompt drifts
into. Stage one (a text model, in webapi) writes that brief; build_prompt()
turns it into the paragraph the image model sees.

Env:
  GEMINI_API_KEY / GOOGLE_API_KEY   required — without it the feature is off
  LEARN_IMAGE_MODEL                 default gemini-3-pro-image
  LEARN_IMAGE_SIZE                  default 1K
  LEARN_IMAGE_TIMEOUT               default 120 (seconds)
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_MODEL = "gemini-3-pro-image"

# USD per generated image, matched by model-id prefix. Gemini bills images per
# image (plus a trivial amount of prompt tokens we don't chase). Longest prefix
# first — "gemini-3.1-flash-lite-image" also starts with "gemini-3.1-flash".
PRICES = [
    ("gemini-3.1-flash-lite-image", 0.0336),
    ("gemini-3.1-flash-image", 0.067),
    ("gemini-3-pro-image", 0.134),
    ("gemini-2.5-flash-image", 0.039),
]
FALLBACK_PRICE = 0.134

# what the Gemini image config accepts; anything else is coerced to the default
ASPECTS = {"1:1", "3:2", "2:3", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}
DEFAULT_ASPECT = "4:3"
SIZES = {"1K", "2K", "4K"}

# The figure kinds stage one may pick. Each maps to the noun the image model
# reads best and the shape that kind of idea actually wants: a process is wide,
# a stack is tall, a single object is squarish.
KINDS = {
    "structure": ("labelled cut-away diagram", "4:3"),
    "process": ("left-to-right process diagram", "16:9"),
    "comparison": ("side-by-side comparison diagram", "16:9"),
    "relation": ("labelled relationship diagram", "4:3"),
    "layers": ("labelled stacked-layer diagram", "3:4"),
    "concrete": ("clear illustration of the object itself", "4:3"),
    "scale": ("labelled diagram comparing sizes", "16:9"),
}
DEFAULT_KIND = "structure"


class ImageError(Exception):
    """Anything that stopped a picture being made. webapi turns it into an
    ApiError; the status rides along so a missing key (500, the operator's
    problem) reads differently from a refusal (502, the model's)."""

    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def api_key() -> str:
    return (os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY") or "").strip()


def available() -> bool:
    """Whether the app should offer the button at all. Both backends report
    this from /api/me so the chip never shows an action that can only fail."""
    return bool(api_key())


def model_name() -> str:
    return os.environ.get("LEARN_IMAGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def image_size() -> str:
    size = os.environ.get("LEARN_IMAGE_SIZE", "1K").strip().upper()
    return size if size in SIZES else "1K"


def price_of(model: str) -> float:
    for prefix, price in PRICES:
        if model.startswith(prefix):
            return price
    return FALLBACK_PRICE


# --------------------------------------------------------------------------- #
# the prompt
# --------------------------------------------------------------------------- #
def clean_aspect(value, kind: str = "") -> str:
    """The requested aspect if it's one Gemini takes, else the one this kind of
    figure wants, else the default."""
    if isinstance(value, str) and value.strip() in ASPECTS:
        return value.strip()
    return KINDS.get(kind, (None, DEFAULT_ASPECT))[1]


def _bullets(items: list) -> str:
    return "\n".join(f"- {item}" for item in items)


def build_prompt(brief: dict) -> str:
    """Turn stage one's brief into the paragraph the image model sees.

    Every section here exists because of a specific failure mode:

    * WHAT/LAYOUT — an image model given no arrangement invents a pretty one,
      and a pretty arrangement of a process is a wrong arrangement.
    * LABELS — the loudest rule in the prompt, because unrequested text is the
      single most common way a generated diagram becomes worse than nothing:
      it comes out as confident-looking gibberish and a reader trusts it. A
      short explicit whitelist, spelled out, is what suppresses it.
    * STYLE — "flat vector textbook figure" is the one phrase that reliably
      keeps the model away from photoreal 3-D renders, which look impressive
      and explain nothing.
    * ACCURACY — an invented part drawn confidently is the failure that costs
      the reader most, so the instruction is explicitly "omit rather than
      invent".
    """
    kind = brief.get("kind") if brief.get("kind") in KINDS else DEFAULT_KIND
    noun = KINDS[kind][0]
    subject = str(brief.get("subject") or "").strip()
    layout = str(brief.get("layout") or "").strip()
    elements = [str(x).strip() for x in (brief.get("elements") or []) if str(x).strip()]
    labels = [str(x).strip() for x in (brief.get("labels") or []) if str(x).strip()]
    avoid = str(brief.get("avoid") or "").strip()

    out = [
        f"A clean, flat, two-dimensional {noun} for a study guide. "
        f"It illustrates exactly one idea: {subject}",
        "",
        "WHAT TO SHOW",
        _bullets(elements) if elements else "- " + subject,
    ]
    if layout:
        out += ["", "LAYOUT", layout]

    out += ["", "LABELS — follow this strictly."]
    if labels:
        quoted = ", ".join(f'"{lab}"' for lab in labels)
        out += [
            f"Write these {len(labels)} labels and no others, spelled exactly as "
            f"given: {quoted}.",
            "Each label is short, horizontal, in a clean bold sans-serif, large "
            "enough to read at a glance, in a colour that contrasts strongly with "
            "whatever sits behind it, placed beside or inside the thing it names "
            "(a thin leader line where that would otherwise be ambiguous).",
        ]
    else:
        out.append("Write no text at all anywhere in the image.")
    out.append(
        "Write NO other text of any kind: no title, no caption, no legend, no "
        "key, no numbers, no arrows with words on them, no units, no watermark, "
        "no signature, no URL, no sentences, no paragraphs, no lorem ipsum, no "
        "decorative lettering. Any word not on the list above is an error. "
        "Prefer empty space to invented text."
    )

    out += [
        "",
        "STYLE",
        "Flat vector illustration in the style of a well-made textbook figure. "
        "Bold, clean outlines; a small palette of three or four flat colours "
        "plus white; generous whitespace; a plain off-white background. No "
        "gradients, no drop shadows, no 3-D bevels, no glow, no reflections, no "
        "photorealism, no painterly or sketchy texture, no background scenery, "
        "no application windows or user-interface chrome, no border or frame "
        "around the image. High contrast throughout — this is read by someone "
        "with dyslexia, often on a phone.",
        "",
        "ACCURACY",
        "This figure has to be true. Draw only what is described above; if "
        "something cannot be shown honestly, leave it out rather than inventing "
        "a plausible-looking stand-in. Show no people unless the idea is about "
        "people.",
    ]
    if avoid:
        out.append(f"Specifically avoid: {avoid}")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# the call
# --------------------------------------------------------------------------- #
def _first_inline_image(data: dict) -> "tuple[str, str] | None":
    """(base64, mime) from a generateContent reply.

    Tolerant of both spellings the API has shipped (inlineData / inline_data)
    and of a reply that leads with a text part before the image.
    """
    for candidate in (data.get("candidates") or []):
        content = candidate.get("content") or {}
        for part in (content.get("parts") or []):
            blob = part.get("inlineData") or part.get("inline_data")
            if not isinstance(blob, dict):
                continue
            b64 = blob.get("data")
            if isinstance(b64, str) and b64:
                mime = blob.get("mimeType") or blob.get("mime_type") or "image/png"
                return b64, str(mime)
    return None


def _refusal(data: dict) -> str:
    """Why nothing came back, in the model's own words where it gave any."""
    fb = data.get("promptFeedback") or {}
    if fb.get("blockReason"):
        return f"the image model declined this request ({fb['blockReason']})"
    for candidate in (data.get("candidates") or []):
        reason = candidate.get("finishReason") or ""
        if reason and reason not in ("STOP", "MAX_TOKENS"):
            return f"the image model stopped without drawing anything ({reason})"
        for part in ((candidate.get("content") or {}).get("parts") or []):
            text = str(part.get("text") or "").strip()
            if text:
                return "the image model replied with words instead of a picture: " \
                       + text[:200]
    return "the image model returned no image — try again, or reword the selection"


def generate(prompt: str, aspect: str = DEFAULT_ASPECT) -> tuple:
    """(base64 image, mime type, cost in USD). Raises ImageError."""
    key = api_key()
    if not key:
        raise ImageError(
            "GEMINI_API_KEY is not set on the server — add it (locally: export "
            "it before `learn --web`; hosted: `vercel env add GEMINI_API_KEY "
            "production`) and the 🖼 image button turns itself on",
            500,
        )
    model = model_name()
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect if aspect in ASPECTS else DEFAULT_ASPECT,
                "imageSize": image_size(),
            },
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{API_ROOT}/{model}:generateContent",
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    timeout = float(os.environ.get("LEARN_IMAGE_TIMEOUT", "120"))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ImageError(_http_error(exc, model), 502) from exc
    except urllib.error.URLError as exc:
        raise ImageError(f"could not reach the Gemini API: {exc.reason}", 502) from exc
    except TimeoutError as exc:
        raise ImageError(f"the image model took longer than {timeout:.0f}s", 504) from exc
    except json.JSONDecodeError as exc:
        raise ImageError("the Gemini API returned something unreadable", 502) from exc

    hit = _first_inline_image(data)
    if not hit:
        raise ImageError(_refusal(data), 502)
    b64, mime = hit
    return b64, mime, price_of(model)


def _http_error(exc: "urllib.error.HTTPError", model: str) -> str:
    try:
        detail = json.loads(exc.read().decode("utf-8"))
        message = str((detail.get("error") or {}).get("message") or "").strip()
    except Exception:  # pragma: no cover - the body is best-effort
        message = ""
    if exc.code in (401, 403):
        return "the Gemini API rejected the key — check GEMINI_API_KEY" + \
               (f" ({message})" if message else "")
    if exc.code == 404:
        return f'no image model called "{model}" — set LEARN_IMAGE_MODEL to one ' \
               f'that exists (default: {DEFAULT_MODEL})'
    if exc.code == 429:
        # Two very different things arrive as 429, and telling a reader to
        # "wait and retry" when the real answer is "this will never work
        # until you enable billing" is the worse of the two failures. Google
        # publishes no free-tier quota for image models at all, so a project
        # without billing reports "limit: 0" — permanent, not transient.
        if "limit: 0" in message or "free_tier" in message:
            return (
                f'"{model}" has no quota on this Gemini key — image generation '
                "is a paid feature, so the key's Google Cloud project needs "
                "billing enabled (https://ai.dev/rate-limit shows the limits). "
                "Everything else in the app is unaffected."
            )
        return "the Gemini API is rate limiting — wait a moment and try again"
    return f"Gemini API error {exc.code}" + (f": {message}" if message else "")
