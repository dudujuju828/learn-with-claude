"""Export a C++ source file to a dyslexia-friendly, line-by-line HTML page.

The page reuses the knowledge-tree export's shell — same fonts, colour themes,
size/spacing controls, arrow-key line stepper, focus line, invert on step and
read aloud — with the source rendered one row per line (line number + code).
The stepper works on it automatically because it enumerates rendered line
boxes, and every source line is one.

Syntax colouring is deliberately light and reuses the theme's existing accent
variables, so it stays readable in every theme including dark: keywords (blue),
strings (green), numbers (magenta), comments (muted), preprocessor (amber).
"""

from __future__ import annotations

import html as _html
import re

from .export_html import _HEAD, _SCRIPT, toolbar_html

_KEYWORDS = frozenset("""
alignas alignof and and_eq asm auto bitand bitor bool break case catch char
char8_t char16_t char32_t class co_await co_return co_yield compl concept
const consteval constexpr constinit const_cast continue decltype default
delete do double dynamic_cast else enum explicit export extern false final
float for friend goto if inline int long mutable namespace new noexcept not
not_eq nullptr operator or or_eq override private protected public
reinterpret_cast requires return short signed sizeof static static_assert
static_cast struct switch template this thread_local throw true try typedef
typeid typename union unsigned using virtual void volatile wchar_t while
xor xor_eq
""".split())

# One alternation, scanned left to right: whichever token starts first wins,
# so a // inside a string stays a string and a "quote" inside a comment stays
# a comment.
_TOKEN = re.compile(
    r"//.*"                    # line comment
    r"|/\*.*?\*/"              # block comment, closed on this line
    r"|/\*.*"                  # block comment, left open
    r'|"(?:[^"\\]|\\.)*"'      # string literal
    r"|'(?:[^'\\]|\\.)*'"      # char literal
    r"|[A-Za-z_]\w*"           # identifier / keyword
    r"|\d[\w'.]*"              # number
)

_DIRECTIVE = re.compile(r"^\s*#\s*\w*")


def _esc(s: str) -> str:
    return _html.escape(s or "")


def _classify(tok: str) -> "str | None":
    if tok.startswith(("//", "/*")):
        return "cmt"
    if tok[0] in "\"'":
        return "str"
    if tok[0].isdigit():
        return "num"
    if tok in _KEYWORDS:
        return "kw"
    return None


def _mark_line(line: str, in_block: bool) -> "tuple[str, bool]":
    """Render one source line to HTML, carrying open /* ... */ state across
    lines. Returns (html, still_in_block)."""
    out = []
    pos = 0
    if in_block:
        end = line.find("*/")
        if end == -1:
            return f'<span class="cmt">{_esc(line)}</span>', True
        out.append(f'<span class="cmt">{_esc(line[: end + 2])}</span>')
        pos = end + 2
    else:
        d = _DIRECTIVE.match(line)
        if d:
            out.append(f'<span class="pre">{_esc(d.group(0))}</span>')
            pos = d.end()

    idx = pos
    for m in _TOKEN.finditer(line, pos):
        if m.start() > idx:
            out.append(_esc(line[idx : m.start()]))
        tok = m.group(0)
        cls = _classify(tok)
        if cls:
            out.append(f'<span class="{cls}">{_esc(tok)}</span>')
        else:
            out.append(_esc(tok))
        idx = m.end()
        if tok.startswith("/*") and not tok.endswith("*/"):
            return "".join(out), True
    out.append(_esc(line[idx:]))
    return "".join(out), False


def code_to_html(title: str, source: str) -> str:
    lines = source.splitlines() or [""]
    rows = []
    in_block = False
    for i, line in enumerate(lines, 1):
        marked, in_block = _mark_line(line, in_block)
        rows.append(
            f'<div class="cl" id="L{i}"><span class="ln">{i}</span>'
            f'<span class="lt">{marked}</span></div>'
        )
    meta = f'<p class="muted">{len(lines)} lines · use the arrow keys with the ruler or focus line to step through</p>'
    return (
        '<!doctype html><html lang="en"><head>'
        + _HEAD.format(title=_esc(title))
        + '</head><body><div class="wrap">'
        + toolbar_html()
        + f"<h1>🧾 {_esc(title)}</h1>"
        + meta
        + '<div class="code">'
        + "".join(rows)
        + "</div></div>"
        + '<div id="ruler"></div>'
        + _SCRIPT
        + "</body></html>"
    )
