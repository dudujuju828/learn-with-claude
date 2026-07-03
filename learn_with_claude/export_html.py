"""Export a knowledge tree to a self-contained, dyslexia-friendly HTML page.

Accessibility choices (per British Dyslexia Association style guidance):
  * dyslexia-friendly typefaces with an in-page switcher — OpenDyslexic, Lexend,
    Atkinson Hyperlegible, Comic Sans — plus a system fallback;
  * cream background and dark-but-not-black text (avoids harsh contrast glare);
  * large text, 1.7 line-height, extra letter/word spacing, ~64-char measure;
  * left-aligned (never justified), no italics, generous whitespace;
  * adjustable text size and line spacing via the toolbar.
"""

from __future__ import annotations

import html as _html
import re

from .render import space_sentences

# Google Fonts reliably serves Lexend + Atkinson Hyperlegible; OpenDyslexic is
# pulled from jsdelivr. If any fail to load, the font stack falls back to
# Comic Sans / Verdana, which are themselves dyslexia-friendly.
_HEAD = """\
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible:wght@400;700&family=Lexend:wght@400;700&display=swap" rel="stylesheet">
<style>
@font-face {{
  font-family:'OpenDyslexic';
  src:url('https://cdn.jsdelivr.net/npm/open-dyslexic@1.0.3/woff/OpenDyslexic-Regular.woff') format('woff');
  font-weight:normal; font-display:swap;
}}
@font-face {{
  font-family:'OpenDyslexic';
  src:url('https://cdn.jsdelivr.net/npm/open-dyslexic@1.0.3/woff/OpenDyslexic-Bold.woff') format('woff');
  font-weight:bold; font-display:swap;
}}
:root{{
  --bg:#fbf6ea; --fg:#2c2620; --muted:#6f6657; --line:#e7dcc7; --card:#fffdf6;
  --think:#8a6d12; --ask:#1c6b46; --ans:#1b4f86; --term:#8a2b6b;
  --fs:18px; --lh:1.75; --measure:64ch;
}}
*{{box-sizing:border-box}}
body{{
  margin:0; background:var(--bg); color:var(--fg);
  font-family:var(--font,'OpenDyslexic'),'Lexend','Atkinson Hyperlegible','Comic Sans MS',Verdana,Tahoma,sans-serif;
  font-size:var(--fs); line-height:var(--lh);
  letter-spacing:.02em; word-spacing:.07em; text-align:left;
}}
.wrap{{max-width:calc(var(--measure) + 7rem); margin:0 auto; padding:1rem 1.25rem 6rem;}}
h1{{font-size:1.7rem; line-height:1.3;}}
h2{{font-size:1.3rem; line-height:1.3; margin-top:0;}}
p{{max-width:var(--measure); margin:.5rem 0;}}
a{{color:var(--ans);}}
.muted{{color:var(--muted);}}
.toolbar{{
  position:sticky; top:0; z-index:5; background:var(--bg);
  border-bottom:1px solid var(--line); padding:.7rem 0; margin-bottom:1.4rem;
  display:flex; gap:.5rem; flex-wrap:wrap; align-items:center;
}}
.toolbar label{{color:var(--muted); font-size:.85rem;}}
.toolbar button, .toolbar select{{
  font-family:inherit; font-size:.9rem; padding:.32rem .6rem;
  border:1px solid var(--line); background:var(--card); color:var(--fg);
  border-radius:.45rem; cursor:pointer;
}}
.map{{background:var(--card); border:1px solid var(--line); border-radius:.8rem; padding:1rem 1.3rem; margin:1rem 0 1.8rem;}}
.map ul{{list-style:none; margin:.2rem 0; padding-left:1.1rem; border-left:2px solid var(--line);}}
.map li{{margin:.35rem 0;}}
.map a{{text-decoration:none;}}
.node{{background:var(--card); border:1px solid var(--line); border-radius:.9rem; padding:1.2rem 1.5rem; margin:1.8rem 0;}}
.crumb{{color:var(--muted); font-size:.92rem; margin:.1rem 0 1rem;}}
.turn{{padding:1.1rem 0; border-top:1px dashed var(--line);}}
.turn:first-of-type{{border-top:none;}}
.label{{font-weight:bold; margin:.1rem 0 .45rem;}}
.block{{border-left:5px solid var(--line); padding:.15rem 0 .15rem 1rem; margin:.2rem 0 1.1rem;}}
.block.think .label{{color:var(--think);}} .block.think{{border-color:var(--think);}}
.block.ask .label{{color:var(--ask);}} .block.ask{{border-color:var(--ask);}}
.block.ans .label{{color:var(--ans);}} .block.ans{{border-color:var(--ans);}}
.term{{display:inline-block; background:#f7e6f1; color:var(--term);
  border:1px solid #e8cbe0; border-radius:.45rem; padding:.12rem .55rem; font-weight:bold; margin:.2rem 0 1rem;}}
pre{{background:#f3ecda; border:1px solid var(--line); border-radius:.55rem; padding:.85rem; overflow:auto; line-height:1.5;}}
code{{font-family:'Cascadia Code',Consolas,'Courier New',monospace; font-size:.95em; letter-spacing:0;}}
.conf{{color:var(--muted); font-weight:normal; font-size:.85em;}}
</style>"""

_SCRIPT = """\
<script>
const root = document.documentElement;
function setFont(v){ root.style.setProperty('--font', v); }
function bumpSize(d){
  const cur = parseFloat(getComputedStyle(root).getPropertyValue('--fs')) || 18;
  root.style.setProperty('--fs', Math.min(28, Math.max(14, cur + d)) + 'px');
}
function bumpLine(d){
  const cur = parseFloat(getComputedStyle(root).getPropertyValue('--lh')) || 1.75;
  root.style.setProperty('--lh', Math.min(2.4, Math.max(1.3, cur + d)).toFixed(2));
}
</script>"""


def _esc(s: str) -> str:
    return _html.escape(s or "")


def _inline_md(seg: str) -> str:
    seg = _esc(seg)
    seg = re.sub(r"`([^`]+)`", r"<code>\1</code>", seg)
    seg = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", seg)
    paras = [p.strip() for p in re.split(r"\n\s*\n", seg) if p.strip()]
    return "".join("<p>" + p.replace("\n", "<br>") + "</p>" for p in paras) or "<p></p>"


def _md_lite(text: str) -> str:
    """Tiny, safe markdown -> HTML: fenced code, inline code, bold, paragraphs."""
    parts = re.split(r"```[a-zA-Z0-9]*\n?(.*?)```", text or "", flags=re.S)
    out = []
    for i, seg in enumerate(parts):
        if i % 2 == 1:
            out.append("<pre><code>" + _esc(seg.rstrip("\n")) + "</code></pre>")
        elif seg.strip():
            out.append(_inline_md(seg))
    return "".join(out) or "<p></p>"


def _turn_html(t: dict) -> str:
    parts = ['<div class="turn">']
    conf = (f' <span class="conf">· confidence {t["confidence"]}%</span>'
            if t.get("confidence") is not None else "")
    parts.append(f'<div class="muted">Turn {t["turn"]}{conf}</div>')
    if t.get("thinking"):
        parts.append(
            '<div class="block think"><div class="label">💭 Thinking to myself</div>'
            f'<p>{_esc(t["thinking"])}</p></div>'
        )
    if t.get("new_term"):
        parts.append(f'<div class="term">🔍 New word I hit: {_esc(t["new_term"])}</div>')
    parts.append(
        '<div class="block ask"><div class="label">🙋 I ask Claude</div>'
        f'<p>{_esc(t["action"])}</p></div>'
    )
    if t.get("tutor"):
        parts.append(
            '<div class="block ans"><div class="label">📘 Claude answers</div>'
            f'{_md_lite(space_sentences(t["tutor"]))}</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def tree_to_html(tree) -> str:
    title = f"Knowledge tree — {tree.root_topic}"

    # navigation map (nested list with anchor links)
    def nav(nid: int) -> str:
        node = tree.nodes[nid]
        conf = f"{node.final_confidence}%" if node.final_confidence is not None else "—"
        meta = f" — {len(node.turns)} turns, confidence {conf}"
        item = f'<li><a href="#node-{node.id}">[{node.id}] {_esc(node.label)}</a>'\
               f'<span class="muted">{_esc(meta)}</span>'
        if node.children:
            item += "<ul>" + "".join(nav(c) for c in node.children) + "</ul>"
        return item + "</li>"

    nav_html = f"<ul>{nav(tree.root_id)}</ul>" if tree.root_id is not None else ""

    # node sections (depth-first)
    sections = []

    def emit(nid: int) -> None:
        node = tree.nodes[nid]
        crumb = _esc(tree.breadcrumb(node.id))
        origin = ("" if node.is_root
                  else f' <span class="muted">(↳ from turn {node.branch_from_turn} '
                       f'of node [{node.parent_id}])</span>')
        body = [f'<section class="node" id="node-{node.id}">',
                f'<h2>[{node.id}] {_esc(node.label)}{origin}</h2>',
                f'<div class="crumb">{crumb}</div>']
        if node.focus:
            body.append(f'<div class="muted">Re-investigating: {_esc(node.focus)}</div>')
        body.extend(_turn_html(t) for t in node.turns)
        body.append("</section>")
        sections.append("".join(body))
        for c in node.children:
            emit(c)

    if tree.root_id is not None:
        emit(tree.root_id)

    toolbar = (
        '<div class="toolbar">'
        '<label for="font">Font</label>'
        '<select id="font" onchange="setFont(this.value)">'
        '<option value="OpenDyslexic">OpenDyslexic</option>'
        '<option value="Lexend">Lexend</option>'
        '<option value="Atkinson Hyperlegible">Atkinson Hyperlegible</option>'
        '<option value="Comic Sans MS">Comic Sans</option>'
        '<option value="system-ui">System</option>'
        "</select>"
        '<button onclick="bumpSize(2)" title="Bigger text">A+</button>'
        '<button onclick="bumpSize(-2)" title="Smaller text">A−</button>'
        '<button onclick="bumpLine(0.15)" title="More line spacing">↕ more</button>'
        '<button onclick="bumpLine(-0.15)" title="Less line spacing">↕ less</button>'
        "</div>"
    )

    meta = (f'<p class="muted">Created {_esc(tree.created)} · {len(tree.nodes)} '
            f'investigations · total cost ${tree.total_cost():.4f}</p>')

    return (
        "<!doctype html><html lang=\"en\"><head>"
        + _HEAD.format(title=_esc(title))
        + "</head><body><div class=\"wrap\">"
        + toolbar
        + f"<h1>🌳 {_esc(tree.root_topic)}</h1>"
        + meta
        + '<div class="map"><div class="label">Map of what I explored</div>'
        + nav_html
        + "</div>"
        + "".join(sections)
        + "</div>"
        + _SCRIPT
        + "</body></html>"
    )
