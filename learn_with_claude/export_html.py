"""Export a knowledge tree to a self-contained, dyslexia-friendly HTML page.

Accessibility choices (per British Dyslexia Association style guidance):
  * dyslexia-friendly typefaces with an in-page switcher — OpenDyslexic, Lexend,
    Atkinson Hyperlegible, Comic Sans — plus a system fallback;
  * cream background and dark-but-not-black text (avoids harsh contrast glare),
    plus alternative colour themes (soft blue / soft green / grey / dark) since
    tinted backgrounds help many dyslexic readers;
  * large text, 1.7 line-height, extra letter/word spacing, ~64-char measure;
  * left-aligned (never justified), no italics, generous whitespace;
  * toolbar controls for text size, line spacing (up to ~4x), letter spacing
    and word spacing;
  * a "sentence per line" toggle: every sentence starts on its own line (each
    sentence is wrapped at export in a <span class="sent"> the toggle turns
    into a block);
  * a reading ruler: a tinted band steered with the arrow keys only (the mouse
    never moves it), stepping through the text one visual line at a time (line
    boxes are enumerated with the Range API) with the current line centred;
  * an optional "invert on step" effect: each arrow-key ruler step flips the
    page to its inverse colours and back (a strong visual pacing cue);
  * a "focus line" mode (typoscope): everything except the current line is
    masked out, via a huge opaque box-shadow around the (full-width) ruler
    band. It works standalone — the band itself is invisible and the revealed
    line acts as the implicit ruler — or combined with the ruler's amber tint;
  * click-to-read-aloud via the browser's built-in speech synthesis;
  * all settings persist in localStorage across reloads.
"""

from __future__ import annotations

import html as _html
import json
import os
import re
from pathlib import Path

from .knowledge import apply_asides
from .render import space_sentences

# "Ask AI": the exported page can query DeepSeek about the highlighted line.
# The key is read at EXPORT time from the environment or ~/.deepseek_key —
# never hardcoded here — and baked into the generated HTML so the browser can
# call the API directly. Exported pages therefore contain the key: keep them
# private (the knowledge dir is gitignored for this reason).
DEEPSEEK_MODEL = "deepseek-v4-pro"


def _deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        return (Path.home() / ".deepseek_key").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def ai_config_html() -> str:
    cfg = {"key": _deepseek_key(), "model": os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_MODEL)}
    return f"<script>window.AI = {json.dumps(cfg)};</script>"

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
  --term-bg:#f7e6f1; --term-line:#e8cbe0; --pre-bg:#f3ecda;
  --fs:18px; --lh:1.75; --ls:.02em; --ws:.07em; --measure:64ch;
}}
*{{box-sizing:border-box}}
body{{
  margin:0; background:var(--bg); color:var(--fg);
  font-family:var(--font,'OpenDyslexic'),'Lexend','Atkinson Hyperlegible','Comic Sans MS',Verdana,Tahoma,sans-serif;
  font-size:var(--fs); line-height:var(--lh);
  letter-spacing:var(--ls); word-spacing:var(--ws); text-align:left;
}}
/* Tall bottom padding so the teleprompter can centre even the last line. */
.wrap{{max-width:calc(var(--measure) + 7rem); margin:0 auto; padding:1rem 1.25rem 55vh;}}
h1{{font-size:1.7rem; line-height:1.3;}}
h2{{font-size:1.3rem; line-height:1.3; margin-top:0;}}
p{{max-width:var(--measure); margin:.5rem 0;}}
a{{color:var(--ans);}}
.muted{{color:var(--muted);}}
.toolbar{{
  position:sticky; top:0; z-index:50; background:var(--bg);
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
.term{{display:inline-block; background:var(--term-bg); color:var(--term);
  border:1px solid var(--term-line); border-radius:.45rem; padding:.12rem .55rem; font-weight:bold; margin:.2rem 0 1rem;}}
.askquote{{color:var(--muted); font-style:italic; border-left:3px solid var(--ask);
  padding:.1rem 0 .1rem .6rem; margin:0 0 .5rem;}}
.block.hlt{{border-color:var(--term);}} .block.hlt .label{{color:var(--term);}}
.block.hlt mark{{background:var(--term-bg); color:inherit; border-radius:.25rem; padding:.05rem .2rem;}}
/* generated figures. White behind the picture on every theme on purpose:
   the figure was drawn on an off-white ground, and a dark card around it
   reads as a hole in the page rather than a diagram. */
figure.fig{{margin:.4rem 0 1.2rem; padding:0;}}
figure.fig img{{display:block; width:100%; max-width:34rem; height:auto;
  background:#fff; border:1px solid var(--line); border-radius:.7rem;}}
figure.fig figcaption{{color:var(--muted); font-size:.9em; margin-top:.4rem;
  max-width:34rem;}}
figure.fig .nofig{{border:1px dashed var(--line); border-radius:.7rem;
  padding:.9rem 1rem; color:var(--muted); max-width:34rem;}}
/* the reader's own words, spliced into the sentence they explain. Tinted
   and bracketed so they can never be mistaken, on a later read, for
   something the tutor actually said. */
.aside{{color:var(--term); font-size:.92em;}}
/* the fact landscape */
#facts ul{{margin:.2rem 0; padding-left:1.2rem;}}
#facts li{{margin:.35rem 0;}}
#facts .fkind{{color:var(--muted); font-size:.85em; border:1px solid var(--line);
  border-radius:.35rem; padding:0 .3rem; margin-right:.25rem;}}
details.part{{border:1px solid var(--line); border-radius:.6rem; background:var(--bg);
  margin:.7rem 0; padding:0 .8rem;}}
details.part summary{{cursor:pointer; padding:.45rem 0; color:var(--muted); font-size:.9em;}}
details.part[open] summary{{color:var(--fg);}}
pre{{background:var(--pre-bg); border:1px solid var(--line); border-radius:.55rem; padding:.85rem; overflow:auto; line-height:1.5;}}
code{{font-family:'Cascadia Code',Consolas,'Courier New',monospace; font-size:.95em; letter-spacing:0;}}
.conf{{color:var(--muted); font-weight:normal; font-size:.85em;}}
/* line-by-line source view (seeplusplus) */
.code{{background:var(--card); border:1px solid var(--line); border-radius:.9rem;
  padding:.9rem 0; margin:1.4rem 0; overflow-x:auto;}}
.cl{{display:flex; padding:0 1rem;}}
.ln{{flex:none; min-width:3em; text-align:right; padding-right:1.1em;
  color:var(--muted); user-select:none;}}
.lt{{flex:1; min-width:0; white-space:pre-wrap; word-break:break-word;
  font-family:'Cascadia Code',Consolas,'Courier New',monospace;
  letter-spacing:var(--ls); word-spacing:var(--ws);}}
/* Ask-AI panel */
#ask{{position:fixed; left:0; right:0; bottom:0; z-index:60; display:none;
  background:var(--card); border-top:2px solid var(--line);
  padding:.7rem 1.2rem 1rem; max-height:45vh; overflow:auto;}}
.ask-open #ask{{display:block;}}
#ask-row{{display:flex; gap:.5rem; margin:.5rem 0;}}
#ask-q{{flex:1; font-family:inherit; font-size:1em; color:var(--fg);
  background:var(--bg); border:1px solid var(--line); border-radius:.5rem; padding:.45rem .6rem;}}
#ask button{{font-family:inherit; font-size:.95em; padding:.4rem .8rem; cursor:pointer;
  background:var(--bg); color:var(--fg); border:1px solid var(--line); border-radius:.5rem;}}
#ask-line{{font-family:'Cascadia Code',Consolas,monospace; font-size:.88em;}}
#ask-a{{white-space:pre-wrap; max-width:var(--measure); line-height:1.45;}}
.lt .kw{{color:var(--ans); font-weight:bold;}}
.lt .str{{color:var(--ask);}}
.lt .cmt{{color:var(--muted);}}
.lt .num{{color:var(--term);}}
.lt .pre{{color:var(--think); font-weight:bold;}}
.grp{{display:inline-flex; align-items:center; gap:.3rem; margin-right:.3rem;}}
.toolbar .tog.on{{border-color:var(--ans); box-shadow:inset 0 0 0 2px var(--ans); font-weight:bold;}}
.sent-lines .sent{{display:block; margin:0 0 .6em;}}
.sent-lines p .sent:last-child{{margin-bottom:0;}}
#ruler{{position:fixed; left:0; right:0; top:40%; height:2.6em; display:none;
  background:rgba(255,205,50,.16); border-top:2px solid rgba(226,164,26,.55);
  border-bottom:2px solid rgba(226,164,26,.55); pointer-events:none; z-index:40;}}
.ruler-on #ruler, .mask-on #ruler{{display:block;}}
/* Focus mode: a huge opaque shadow around the full-width ruler band masks
   everything above and below it, leaving only the current line visible. On its
   own the band is invisible — the revealed line IS the ruler; combine with the
   ruler toggle to also tint the line amber. */
.mask-on #ruler{{box-shadow:0 0 0 200vmax var(--bg);}}
.mask-on:not(.ruler-on) #ruler{{background:transparent; border-color:transparent;}}
/* Applied to <html>: the root element is exempt from filter's containing-block
   rule, so the fixed toolbar and ruler keep their viewport positioning. */
.inverted{{filter:invert(1) hue-rotate(180deg);}}
.speak-on .block, .speak-on h1, .speak-on h2, .speak-on .term{{cursor:pointer;}}
.reading{{outline:3px solid var(--ans); outline-offset:4px; border-radius:.4rem;}}
</style>"""

_SCRIPT = """\
<script>
const root = document.documentElement, body = document.body;
window.AI = window.AI || {key:'', model:''};  // baked in by the exporter
const DEFAULTS = {font:'OpenDyslexic', fs:18, lh:1.75, ls:0.02, ws:0.07,
                  theme:'cream', sent:false, ruler:false, speak:false, inv:false,
                  mask:false};
const S = Object.assign({}, DEFAULTS);
const THEMES = {
  cream:{bg:'#fbf6ea', card:'#fffdf6', fg:'#2c2620', line:'#e7dcc7', muted:'#6f6657',
         think:'#8a6d12', ask:'#1c6b46', ans:'#1b4f86', term:'#8a2b6b',
         termbg:'#f7e6f1', termline:'#e8cbe0', prebg:'#f3ecda'},
  blue: {bg:'#e9f1f9', card:'#f6fafd', fg:'#22303c', line:'#cfdfec', muted:'#5c6f80',
         think:'#7a6210', ask:'#176546', ans:'#175a94', term:'#7d2a62',
         termbg:'#f0e2ec', termline:'#dcc3d4', prebg:'#dfeaf3'},
  green:{bg:'#ecf4e9', card:'#f8fbf6', fg:'#26302a', line:'#d4e3cd', muted:'#5f7160',
         think:'#7a6210', ask:'#186a3b', ans:'#1b5e86', term:'#7d2a62',
         termbg:'#eee3ea', termline:'#d9c4d2', prebg:'#e2ecdc'},
  grey: {bg:'#e9e9e7', card:'#f5f5f3', fg:'#26262a', line:'#d2d2cf', muted:'#63635f',
         think:'#77620f', ask:'#1a6244', ans:'#1a5583', term:'#7d2a62',
         termbg:'#ece1e8', termline:'#d6c2d0', prebg:'#dededa'},
  dark: {bg:'#20221f', card:'#2a2d29', fg:'#e9e4da', line:'#44483f', muted:'#a9a294',
         think:'#d9b64a', ask:'#7fd3a4', ans:'#8fbef2', term:'#e29ac7',
         termbg:'#3a2f37', termline:'#5c4653', prebg:'#32352f'}
};
// The ruler machinery (band element, mouse-follow, arrow keys) is active when
// either the visible ruler or focus-line mode is on — focus mode is just the
// ruler with an invisible band and a masking shadow.
function rulerActive(){ return S.ruler || S.mask; }
function apply(){
  const t = THEMES[S.theme] || THEMES.cream;
  const v = {font:S.font, fs:S.fs+'px', lh:S.lh, ls:S.ls+'em', ws:S.ws+'em',
             bg:t.bg, card:t.card, fg:t.fg, line:t.line, muted:t.muted,
             think:t.think, ask:t.ask, ans:t.ans, term:t.term,
             'term-bg':t.termbg, 'term-line':t.termline, 'pre-bg':t.prebg};
  for(const k in v) root.style.setProperty('--'+k, v[k]);
  body.classList.toggle('sent-lines', S.sent);
  body.classList.toggle('ruler-on', S.ruler);
  body.classList.toggle('mask-on', S.mask);
  body.classList.toggle('speak-on', S.speak);
  if(!rulerActive()) document.getElementById('ruler').style.height = '';
  if(!rulerActive() || !S.inv) root.classList.remove('inverted');
  lines = null; lineIdx = -1;  // any setting change may have reflowed the text
  if(!S.speak && window.speechSynthesis) speechSynthesis.cancel();
  document.getElementById('font').value = S.font;
  document.getElementById('theme').value = S.theme;
  for(const [id, on] of [['sent-btn',S.sent],['ruler-btn',S.ruler],['mask-btn',S.mask],
                         ['speak-btn',S.speak],['inv-btn',S.inv]])
    document.getElementById(id).classList.toggle('on', on);
  try{ localStorage.setItem('lwc-a11y', JSON.stringify(S)); }catch(err){}
}
function setS(k, v){ S[k] = v; apply(); }
function bump(k, d, min, max){
  S[k] = Math.min(max, Math.max(min, Math.round((S[k] + d) * 1000) / 1000));
  apply();
}
function resetS(){ Object.assign(S, DEFAULTS); apply(); }

// Reading-ruler line navigation: the ruler is steered ONLY by the arrow keys,
// one *visual* line at a time — the mouse never moves it. Wrapped lines aren't
// elements, so the rendered line boxes are enumerated with the Range API (one
// client rect per line box) and rects that share a top are merged (a line
// broken into several text nodes by <code> or <strong> yields several rects).
let lines = null, lineIdx = -1;
function lineList(){
  if(lines) return lines;
  const buckets = {};
  const walker = document.createTreeWalker(document.querySelector('.wrap'), NodeFilter.SHOW_TEXT);
  const range = document.createRange();
  for(let n = walker.nextNode(); n; n = walker.nextNode()){
    if(!n.nodeValue.trim() || n.parentElement.closest('.toolbar')) continue;
    range.selectNodeContents(n);
    for(const r of range.getClientRects()){
      if(r.height < 4 || r.width < 2) continue;
      const top = r.top + scrollY, bottom = r.bottom + scrollY;
      const key = Math.round(top / 5);
      const b = buckets[key] || buckets[key + 1] || buckets[key - 1];
      if(b){ b.top = Math.min(b.top, top); b.bottom = Math.max(b.bottom, bottom); }
      else buckets[key] = {top: top, bottom: bottom};
    }
  }
  lines = Object.values(buckets).sort((a, b) => a.top - b.top);
  return lines;
}
function stepLine(d){
  const list = lineList();
  if(!list.length) return;
  if(lineIdx < 0){  // first press: start at the first line on screen
    lineIdx = list.findIndex(l => l.bottom > scrollY + 8);
    if(lineIdx < 0) lineIdx = 0;
  } else {
    lineIdx = Math.min(list.length - 1, Math.max(0, lineIdx + d));
  }
  const ln = list[lineIdx];
  // Teleprompter: keep the current line centred; the text scrolls under the
  // band. The browser clamps at the document edges, and the band placement
  // below uses the post-scroll scrollY, so it lands on the line either way.
  scrollTo({top: Math.max(0, (ln.top + ln.bottom) / 2 - innerHeight / 2)});
  const r = document.getElementById('ruler');
  r.style.top = (ln.top - scrollY - 3) + 'px';
  r.style.height = (ln.bottom - ln.top + 6) + 'px';
  if(S.inv) root.classList.toggle('inverted');
}
addEventListener('resize', () => { lines = null; lineIdx = -1; });
document.addEventListener('keydown', e => {
  if(e.key === 'Escape'){
    if(window.speechSynthesis) speechSynthesis.cancel();
    closeAsk();
  }
  if(!rulerActive() || e.target.closest('select, input, textarea, button')) return;
  if(e.key === 'ArrowRight' || e.key === 'ArrowDown'){ e.preventDefault(); stepLine(1); }
  else if(e.key === 'ArrowLeft' || e.key === 'ArrowUp'){ e.preventDefault(); stepLine(-1); }
  else if(e.key === 'a' || e.key === 'A'){ e.preventDefault(); openAsk(); }
});

// --- Ask AI (DeepSeek) about the line under the ruler ----------------------
const askPanel = document.createElement('div');
askPanel.id = 'ask';
askPanel.innerHTML =
  '<div id="ask-line" class="muted"></div>' +
  '<div id="ask-row">' +
  '<textarea id="ask-q" rows="2" placeholder="Ask about this line\\u2026 (Enter sends, Esc closes, Right Shift toggles back to the ruler)"></textarea>' +
  '<button onclick="sendAsk()">Ask</button>' +
  '<button onclick="closeAsk()" title="Close">\\u2715</button></div>' +
  '<div id="ask-a"></div>';
document.body.appendChild(askPanel);
let askTarget = null;

function currentTarget(){
  const band = document.getElementById('ruler').getBoundingClientRect();
  const y = band.top + band.height / 2;
  const wrap = document.querySelector('.wrap').getBoundingClientRect();
  for(const fx of [0.25, 0.45, 0.65]){
    for(const cand of document.elementsFromPoint(wrap.left + wrap.width * fx, y)){
      const el = cand.closest && (cand.closest('.cl') || cand.closest('.block, h1, h2, .term'));
      if(el) return el;
    }
  }
  return null;
}
function targetInfo(el){
  if(el.classList.contains('cl')){
    const all = Array.from(document.querySelectorAll('.cl'));
    const i = all.indexOf(el);
    const ctx = all.slice(Math.max(0, i - 20), i + 21)
      .map(c => c.querySelector('.ln').textContent.padStart(4) + ' | ' + c.querySelector('.lt').innerText)
      .join('\\n');
    return {label: 'line ' + el.querySelector('.ln').textContent,
            focus: el.querySelector('.lt').innerText, context: ctx};
  }
  return {label: 'highlighted block', focus: el.innerText, context: ''};
}
function openAsk(){
  askTarget = currentTarget();
  document.getElementById('ask-line').textContent = askTarget
    ? targetInfo(askTarget).label + ':  ' + targetInfo(askTarget).focus.trim().slice(0, 120)
    : 'put the ruler or focus line on a line first, then press A (or the \\ud83e\\udd16 button) again';
  body.classList.add('ask-open');
  document.getElementById('ask-q').focus();
}
function closeAsk(){ body.classList.remove('ask-open'); }
async function sendAsk(){
  const out = document.getElementById('ask-a');
  const box = document.getElementById('ask-q');
  const q = box.value.trim();
  if(q.toLowerCase() === 'cls'){ out.textContent = ''; box.value = ''; return; }
  if(!askTarget){ openAsk(); return; }
  if(!q) return;
  if(!AI.key){
    out.textContent = 'No DeepSeek API key was baked into this export. ' +
      'Set DEEPSEEK_API_KEY (or ~/.deepseek_key) and re-export the page.';
    return;
  }
  const info = targetInfo(askTarget);
  box.value = '';  // clear the question as soon as it is sent
  out.textContent = '\\ud83e\\udd16 thinking\\u2026';
  try{
    const res = await fetch('https://api.deepseek.com/chat/completions', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + AI.key},
      body: JSON.stringify({model: AI.model, stream: false, messages: [
        {role: 'system', content:
          'You are a sharp programming tutor answering ONE question about a specific line from a page ' +
          'the user is reading. Give a complete, technically accurate answer: do NOT simplify the content, ' +
          'omit relevant detail, or avoid precise terminology - assume a capable reader who wants the real ' +
          'explanation, and use as many sentences as the question actually needs. ' +
          'The reader is dyslexic, so only the FORMATTING must adapt: keep each sentence short, put every ' +
          'sentence on its own line with a blank line between sentences, and prefer several small chunks ' +
          'over one dense block. Plain text only - no markdown headings or tables.'},
        {role: 'user', content:
          'Page: ' + document.title + '\\n\\n' +
          (info.context ? 'Context:\\n' + info.context + '\\n\\n' : '') +
          'The line I am asking about:\\n' + info.focus + '\\n\\nMy question: ' + q}
      ]})
    });
    const data = await res.json();
    if(!res.ok) throw new Error((data.error && data.error.message) || ('HTTP ' + res.status));
    out.textContent = data.choices[0].message.content;
  }catch(err){
    out.textContent = 'Error: ' + err.message;
  }
}
document.getElementById('ask-q').addEventListener('keydown', e => {
  if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); sendAsk(); }
  if(e.key === 'Escape') closeAsk();
  e.stopPropagation();
});

// Right Shift toggles between ruler control (arrow keys step lines) and the
// AI question box. Only a BARE tap counts — if any other key is pressed while
// it is held, it was being used as a normal modifier (capitals, Shift+Enter).
// Capture phase, so it still sees keys typed inside the textarea.
let rshiftDown = false, rshiftCombo = false;
function toggleAskFocus(){
  const q = document.getElementById('ask-q');
  if(document.activeElement === q) q.blur();  // back to ruler control
  else openAsk();                             // (re)capture the line + focus box
}
document.addEventListener('keydown', e => {
  if(e.key === 'Shift' && e.location === 2){ rshiftDown = true; rshiftCombo = false; }
  else if(rshiftDown) rshiftCombo = true;
}, true);
document.addEventListener('keyup', e => {
  if(e.key === 'Shift' && e.location === 2){
    if(!rshiftCombo) toggleAskFocus();
    rshiftDown = false;
  }
}, true);
document.addEventListener('click', e => {
  if(!S.speak || !window.speechSynthesis) return;
  if(e.target.closest('.toolbar, a')) return;
  const blk = e.target.closest('.block, .cl, h1, h2, .term, .crumb');
  if(!blk) return;
  speechSynthesis.cancel();
  document.querySelectorAll('.reading').forEach(x => x.classList.remove('reading'));
  const u = new SpeechSynthesisUtterance(blk.innerText);
  u.rate = 0.95;
  u.onend = u.onerror = () => blk.classList.remove('reading');
  blk.classList.add('reading');
  speechSynthesis.speak(u);
});
try{ Object.assign(S, JSON.parse(localStorage.getItem('lwc-a11y') || '{}')); }catch(err){}
apply();
</script>"""


def _esc(s: str) -> str:
    return _html.escape(s or "")


# Sentence boundaries are marked with a \x00 placeholder (inserted before
# HTML-escaping), then each sentence is wrapped in <span class="sent">. That
# lets CSS put every sentence on its own line ("sentence per line" toggle) and
# lets JS step the reading ruler sentence by sentence with the arrow keys.
# Unlike render.space_sentences this also accepts lowercase sentence starts,
# because the learner deliberately types in casual lowercase.
_SENT_GAP = re.compile(r"(?<=[.!?])([\"')\]]*)\s+(?=[A-Za-z0-9\"'(\[])")


def _mark(s: str) -> str:
    return _SENT_GAP.sub("\\1\x00", s or "")


def _wrap_sents(inner: str) -> str:
    """Wrap each \x00-separated sentence of rendered inline HTML in a span."""
    parts = [p for p in inner.split("\x00") if p.strip()]
    return " ".join(f'<span class="sent">{p}</span>' for p in parts) or inner


def _esc_sent(s: str) -> str:
    """Escape text and wrap each of its sentences in a navigable span."""
    return _wrap_sents(_esc(_mark(s)))


def _inline_md(seg: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n", seg or "") if p.strip()]
    out = []
    for p in paras:
        p = _esc(_mark(p))
        # Neutralise markers inside code/bold so a sentence span never splits
        # an open tag (restore the space the marker replaced).
        p = re.sub(r"`([^`]+)`",
                   lambda m: "<code>" + m.group(1).replace("\x00", " ") + "</code>", p)
        p = re.sub(r"\*\*([^*]+)\*\*",
                   lambda m: "<strong>" + m.group(1).replace("\x00", " ") + "</strong>", p)
        out.append("<p>" + _wrap_sents(p.replace("\n", "<br>")) + "</p>")
    return "".join(out) or "<p></p>"


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


def note_md(text: str) -> str:
    """The reader's own notes, which are written in a small markdown subset
    (the notes editor has a toolbar for it): headings, bullet and numbered
    lists, quotes, rules, bold/italic/underline/code. Same escape-first
    discipline as everything else here — only the tags built below can reach
    the page. Mirrors noteHtml() in public/index.html.
    """
    def inline(s: str) -> str:
        s = _esc(s)
        s = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", s)
        s = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(^|[^*\w])\*([^*\n]+)\*", r"\1<em>\2</em>", s)
        s = re.sub(r"(^|[^_\w])_([^_\n]+)_", r"\1<em>\2</em>", s)
        return re.sub(r"&lt;u&gt;(.*?)&lt;/u&gt;", r"<u>\1</u>", s, flags=re.S)

    html: list = []
    para: list = []
    list_tag = None

    def flush_para():
        if para:
            html.append("<p>" + "<br>".join(inline(x) for x in para) + "</p>")
            para.clear()

    def flush_list():
        nonlocal list_tag
        if list_tag:
            html.append(f"</{list_tag}>")
            list_tag = None

    def open_list(tag):
        nonlocal list_tag
        if list_tag != tag:
            flush_list()
            html.append(f"<{tag}>")
            list_tag = tag

    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            flush_list()
            continue
        m = re.match(r"^\s{0,3}(#{1,4})\s+(.*)$", line)
        if m:
            flush_para()
            flush_list()
            html.append(f"<h{min(6, len(m.group(1)) + 1)}>{inline(m.group(2))}"
                        f"</h{min(6, len(m.group(1)) + 1)}>")
            continue
        if re.match(r"^\s{0,3}(---|\*\*\*|___)\s*$", line):
            flush_para()
            flush_list()
            html.append("<hr>")
            continue
        m = re.match(r"^\s{0,3}[-*+]\s+(.*)$", line)
        if m:
            flush_para()
            open_list("ul")
            html.append(f"<li>{inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s{0,3}\d+[.)]\s+(.*)$", line)
        if m:
            flush_para()
            open_list("ol")
            html.append(f"<li>{inline(m.group(1))}</li>")
            continue
        m = re.match(r"^\s{0,3}>\s?(.*)$", line)
        if m:
            flush_para()
            flush_list()
            html.append(f"<blockquote>{inline(m.group(1))}</blockquote>")
            continue
        flush_list()
        para.append(line)
    flush_para()
    flush_list()
    return "".join(html)


def toolbar_html() -> str:
    """The reading-aids toolbar, shared by the tree export and the source-code
    export (seeplusplus)."""
    return (
        '<div class="toolbar">'
        '<span class="grp"><label for="font">Font</label>'
        '<select id="font" onchange="setS(\'font\', this.value)">'
        '<option value="OpenDyslexic">OpenDyslexic</option>'
        '<option value="Lexend">Lexend</option>'
        '<option value="Atkinson Hyperlegible">Atkinson Hyperlegible</option>'
        '<option value="Comic Sans MS">Comic Sans</option>'
        '<option value="system-ui">System</option>'
        "</select></span>"
        '<span class="grp"><label for="theme">Colours</label>'
        '<select id="theme" onchange="setS(\'theme\', this.value)">'
        '<option value="cream">Cream</option>'
        '<option value="blue">Soft blue</option>'
        '<option value="green">Soft green</option>'
        '<option value="grey">Grey</option>'
        '<option value="dark">Dark</option>'
        "</select></span>"
        '<span class="grp"><label>Text</label>'
        '<button onclick="bump(\'fs\', -2, 14, 40)" title="Smaller text">A−</button>'
        '<button onclick="bump(\'fs\', 2, 14, 40)" title="Bigger text">A+</button></span>'
        '<span class="grp"><label>Lines</label>'
        '<button onclick="bump(\'lh\', -0.25, 1.3, 4)" title="Less space between lines">−</button>'
        '<button onclick="bump(\'lh\', 0.25, 1.3, 4)" title="More space between lines">+</button></span>'
        '<span class="grp"><label>Letters</label>'
        '<button onclick="bump(\'ls\', -0.02, 0, 0.2)" title="Less space between letters">−</button>'
        '<button onclick="bump(\'ls\', 0.02, 0, 0.2)" title="More space between letters">+</button></span>'
        '<span class="grp"><label>Words</label>'
        '<button onclick="bump(\'ws\', -0.05, 0, 0.5)" title="Less space between words">−</button>'
        '<button onclick="bump(\'ws\', 0.05, 0, 0.5)" title="More space between words">+</button></span>'
        '<button id="sent-btn" class="tog" onclick="setS(\'sent\', !S.sent)" '
        'title="Start every sentence on its own line">↵ sentence per line</button>'
        '<button id="ruler-btn" class="tog" onclick="setS(\'ruler\', !S.ruler)" '
        'title="A tinted band you steer with the arrow keys, one line at a '
        'time, keeping the current line centred">🖍 reading ruler</button>'
        '<button id="mask-btn" class="tog" onclick="setS(\'mask\', !S.mask)" '
        'title="Hide everything except the current line — step with the arrow '
        'keys; add the reading ruler if you also want the line tinted">🕶 focus line</button>'
        '<button id="inv-btn" class="tog" onclick="setS(\'inv\', !S.inv)" '
        'title="Flip the page colours to their inverse on every ruler step '
        '(arrow keys), and back on the next">🌓 invert on step</button>'
        '<button id="speak-btn" class="tog" onclick="setS(\'speak\', !S.speak)" '
        'title="Then click any block of text to hear it read aloud (Esc stops)">🔊 read aloud</button>'
        '<button onclick="openAsk()" title="Ask AI (DeepSeek) about the line under the '
        'ruler or focus line — shortcuts: A opens, Right Shift toggles between the '
        'ruler and the question box">🤖 ask AI</button>'
        '<button onclick="resetS()" title="Back to the default settings">reset</button>'
        "</div>"
    )


# A data: URI the browser will actually load, or "". The exported page is
# self-contained by design (it is mailed around, opened offline, kept), so a
# figure either travels inside it or doesn't travel at all — an <img> pointing
# back at the server would be a broken box on every machine but one. The
# client inlines `data` into the tree it POSTs to /api/export_html; a tree
# exported by the CLI has the description but no bytes, and falls back to it.
_DATA_URI_OK = ("image/webp", "image/png", "image/jpeg")


def _figure_src(fig: dict) -> str:
    data = str(fig.get("data") or "")
    if not data:
        return ""
    if data.startswith("data:"):
        return data if data[5:].split(";", 1)[0] in _DATA_URI_OK else ""
    mime = str(fig.get("mime") or "image/webp")
    if mime not in _DATA_URI_OK:
        return ""
    # base64 only — anything else is not something we wrote
    if any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\n\r"
           for c in data[:200]):
        return ""
    return f"data:{mime};base64,{data}"


def _figures_html(figures) -> str:
    out = []
    for fig in figures or []:
        caption = _esc(str(fig.get("caption") or "a figure"))
        alt = _esc(str(fig.get("alt") or fig.get("caption") or "generated figure"))
        src = _figure_src(fig)
        inner = (f'<img src="{src}" alt="{alt}" loading="lazy" decoding="async">'
                 if src else
                 f'<div class="nofig">🖼 {alt}</div>')
        out.append(f'<figure class="fig">{inner}'
                   f'<figcaption>🖼 {caption}</figcaption></figure>')
    return "".join(out)


# The reader's own words go in *inside* the prose, but _md_lite escapes
# before it builds tags — so a <span> spliced in beforehand would come out as
# visible markup. Private-use sentinels pass through the escaper untouched
# (it only rewrites &<>"') and get swapped for the real element afterwards.
_ASIDE_OPEN, _ASIDE_CLOSE = "", ""


def _aside_wrap(words: str) -> str:
    # real brackets, real leading space: the exported page gets read aloud and
    # copied out of, and CSS-drawn punctuation survives neither
    return f" {_ASIDE_OPEN}({words}){_ASIDE_CLOSE}"


def _asides_into(text: str, pending: list) -> str:
    """Splice in whichever pending asides match `text`, removing them from
    `pending` as they land. Shared mutable state across an answer's parts on
    purpose: each aside belongs at exactly ONE place, the same first
    occurrence the browser picks, even when the answer is split into cards."""
    for aside in list(pending):
        after = apply_asides(text, [aside], wrap=_aside_wrap)
        if after != text:
            text = after
            pending.remove(aside)
    return text


def _aside_spans(html: str) -> str:
    return (html.replace(_ASIDE_OPEN, '<span class="aside">')
                .replace(_ASIDE_CLOSE, "</span>"))


def _turn_html(t: dict, highlights=None, figures=None, asides=None) -> str:
    parts = ['<div class="turn">']
    conf = (f' <span class="conf">· confidence {t["confidence"]}%</span>'
            if t.get("confidence") is not None else "")
    parts.append(f'<div class="muted">Turn {t["turn"]}{conf}</div>')
    if t.get("thinking"):
        parts.append(
            '<div class="block think"><div class="label">💭 Thinking to myself</div>'
            f'<p>{_esc_sent(t["thinking"])}</p></div>'
        )
    if t.get("new_term"):
        parts.append(f'<div class="term">🔍 New word I hit: {_esc(t["new_term"])}</div>')
    parts.append(
        '<div class="block ask"><div class="label">🙋 I ask Claude</div>'
        + (f'<div class="askquote">❝ {_esc(t["quote"])}</div>' if t.get("quote") else "")
        + f'<p>{_esc_sent(t["action"])}</p></div>'
    )
    if t.get("tutor"):
        answer_parts = t.get("parts") if isinstance(t.get("parts"), list) else None
        labelled = answer_parts and any(
            isinstance(p, dict) and p.get("label") for p in answer_parts
        )
        pending = list(asides or [])
        if labelled:
            inner = []
            for p in answer_parts:
                if not isinstance(p, dict):
                    continue
                text = str(p.get("text") or "").strip()
                if not text:
                    continue
                body = _md_lite(_asides_into(space_sentences(text), pending))
                label = str(p.get("label") or "").strip()
                if label:
                    inner.append(
                        f'<details class="part" open><summary>{_esc(label)}</summary>{body}</details>'
                    )
                else:
                    inner.append(body)
            answer_html = "".join(inner)
        else:
            answer_html = _md_lite(_asides_into(space_sentences(t["tutor"]), pending))
        parts.append(
            '<div class="block ans"><div class="label">📘 Claude answers</div>'
            f"{_aside_spans(answer_html)}</div>"
        )
    if highlights:
        marks = "".join(f"<p><mark>{_esc(h)}</mark></p>" for h in highlights)
        parts.append(
            f'<div class="block hlt"><div class="label">★ I highlighted</div>{marks}</div>'
        )
    if figures:
        parts.append(_figures_html(figures))
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
    hl_map = tree.highlight_map() if hasattr(tree, "highlight_map") else {}
    img_map = tree.image_map() if hasattr(tree, "image_map") else {}
    aside_map = tree.aside_map() if hasattr(tree, "aside_map") else {}

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
        body.extend(_turn_html(t, hl_map.get((node.id, t.get("turn"))),
                               img_map.get((node.id, t.get("turn"))),
                               aside_map.get((node.id, t.get("turn"))))
                    for t in node.turns)
        body.append("</section>")
        sections.append("".join(body))
        for c in node.children:
            emit(c)

    if tree.root_id is not None:
        emit(tree.root_id)

    toolbar = toolbar_html()

    # ⚡ the factual landscape — reference material, so it gets its own
    # section rather than being threaded through the conversations
    facts_html = ""
    fact_groups = tree.fact_groups() if hasattr(tree, "fact_groups") else []
    if fact_groups:
        def _fact_li(fact: dict) -> str:
            kind = str(fact.get("kind") or "").strip()
            tag = f'<span class="fkind">{_esc(kind)}</span> ' if kind else ""
            return f'<li>{tag}{_esc(str(fact["text"]))}</li>'

        blocks = []
        for name, items in fact_groups:
            rows = "".join(_fact_li(f) for f in items)
            blocks.append('<div class="turn"><div class="block ans">'
                          f'<div class="label">{_esc(name)}</div>'
                          f"<ul>{rows}</ul></div></div>")
        facts_html = (
            '<section class="node" id="facts"><h2>The landscape</h2>'
            '<div class="muted">The facts this topic was mapped out with.</div>'
            + "".join(blocks) + "</section>"
        )

    glossary_html = ""
    defined = sorted(
        (e for e in getattr(tree, "glossary", {}).values()
         if isinstance(e, dict) and e.get("def")),
        key=lambda e: str(e.get("term", "")).lower(),
    )
    if defined:
        def _gloss_label(e: dict) -> str:
            reason = str(e.get("reason") or "").strip()
            term = _esc(e["term"])
            return f"{term} ({_esc(reason)})" if reason and reason != "definition" else term

        entries = "".join(
            f'<div class="turn"><div class="block ans">'
            f'<div class="label">🔍 {_gloss_label(e)}</div>'
            f'<p>{_esc(e["def"])}</p></div></div>'
            for e in defined
        )
        glossary_html = (
            '<section class="node" id="glossary"><h2>Glossary</h2>'
            '<div class="muted">Every word the learner hit, defined.</div>'
            f"{entries}</section>"
        )

    teach = tree.teach_map() if hasattr(tree, "teach_map") else {}
    teach_html = ""
    if teach:
        tags = {"clean": "✓ clean", "close": "≈ close", "gappy": "△ gappy"}
        blocks = []
        for nid in sorted(teach):
            last = teach[nid][-1]
            verdict = str(last.get("verdict") or "").strip()
            tag = tags.get(verdict, "")
            missing = str(last.get("missing") or "").strip()
            blocks.append(
                f'<div class="turn"><div class="block ans">'
                f'<div class="label">🗣 [{nid}] {_esc(tree.nodes[nid].label)}'
                + (f" — {_esc(tag)}" if tag else "") + "</div>"
                f'<p>{_esc(last["text"])}</p>'
                + (f'<p class="muted">The gap that mattered: {_esc(missing)}</p>'
                   if verdict != "clean" and missing else "")
                + "</div></div>"
            )
        teach_html = (
            '<section class="node" id="explainedback"><h2>🗣 Explained back</h2>'
            '<div class="muted">What I could say in my own words, checked by the tutor.</div>'
            + "".join(blocks) + "</section>"
        )

    exams = tree.exam_map() if hasattr(tree, "exam_map") else {}
    exam_html = ""
    if exams:
        blocks = []
        for nid in sorted(exams):
            for exam in exams[nid]:
                total, mx = exam.get("total"), exam.get("max")
                score = f" — {total}/{mx}" if isinstance(total, int) and mx else ""
                sat = str(exam.get("submitted") or "")[:10]
                blocks.append(
                    f'<div class="turn"><div class="block ask"><div class="label">'
                    f'✍ [{nid}] {_esc(tree.nodes[nid].label)}{_esc(score)}'
                    + (f" · {_esc(sat)}" if sat else "") + "</div>"
                    + (f"<p>{_esc(str(exam.get('overall') or '').strip())}</p>"
                       if str(exam.get("overall") or "").strip() else "")
                    + "</div></div>"
                )
                for i, (q, answer, result) in enumerate(tree.exam_rows(exam), 1):
                    marks = result.get("marks")
                    got = (f" — {marks}/{q.get('marks', 10)}"
                           if isinstance(marks, int) else "")
                    feedback = "".join(
                        f'<p class="muted">{_esc(str(result.get(key) or "").strip())}</p>'
                        for key in ("earned", "improve")
                        if str(result.get(key) or "").strip()
                    )
                    blocks.append(
                        f'<div class="turn"><div class="block">'
                        f'<div class="label">Q{i}{_esc(got)}</div>'
                        f"<p>{_esc(q['q'])}</p></div>"
                        f'<div class="block ans"><div class="label">My answer</div>'
                        f"<p>{_esc(answer.strip() or '(left blank)')}</p>"
                        f"{feedback}</div></div>"
                    )
        exam_html = (
            '<section class="node" id="exams"><h2>✍ Exams</h2>'
            '<div class="muted">Written answers under exam conditions, and how they were marked.</div>'
            + "".join(blocks) + "</section>"
        )

    meta = (f'<p class="muted">Created {_esc(tree.created)} · {len(tree.nodes)} '
            f'investigations · total cost ${tree.total_cost():.4f}</p>')

    source = str(getattr(tree, "extras", {}).get("source") or "").strip()
    source_html = ""
    if source:
        paras = "".join(
            "<p>" + "<br>".join(_esc(line) for line in para.split("\n")) + "</p>"
            for para in re.split(r"\n{2,}", source) if para.strip()
        )
        source_html = (
            '<section class="node" id="sourcematerial"><h2>📚 Source material</h2>'
            f'<div class="turn"><div class="block">{paras}</div></div></section>'
        )

    note = (getattr(tree, "note", "") or "").strip()
    note_html = ""
    if note:
        paras = note_md(note)
        note_html = (
            '<section class="node" id="mynotes"><h2>📝 My notes</h2>'
            f'<div class="turn"><div class="block">{paras}</div></div></section>'
        )

    return (
        "<!doctype html><html lang=\"en\"><head>"
        + _HEAD.format(title=_esc(title))
        + "</head><body><div class=\"wrap\">"
        + toolbar
        + f"<h1>🌳 {_esc(tree.root_topic)}</h1>"
        + meta
        + source_html
        + note_html
        + '<div class="map"><div class="label">Map of what I explored</div>'
        + nav_html
        + "</div>"
        + facts_html
        + "".join(sections)
        + glossary_html
        + teach_html
        + exam_html
        + "</div>"
        + '<div id="ruler"></div>'
        + ai_config_html()
        + _SCRIPT
        + "</body></html>"
    )
