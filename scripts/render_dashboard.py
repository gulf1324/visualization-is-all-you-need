#!/usr/bin/env python3
"""Render PROJECT.md into a single read-only HTML dashboard.

    python scripts/render_dashboard.py [PROJECT.md] [-o PROJECT.html] [--open]

The page is a build product: the map data is baked in at generation time and
there is no input element anywhere. Read-only is therefore structural, not a UI
policy — the only way to change what it shows is

    change the code -> update PROJECT.md -> re-run this script

Translations are optional sibling maps: `PROJECT.ko.md` next to `PROJECT.md`
supplies Korean `role:`/`why` text for the same node ids. Inline dual strings
were rejected: they double every ledger entry and the second language rots the
moment someone edits only the first. A sibling file reuses the format as-is and
lets the node-id sets be compared, so drift is caught here and refuses to
build.

Mermaid is loaded from a CDN. Vendoring it would add ~3 MB to a repo whose
whole premise is "no install step"; the page states plainly when it cannot
load.

Exit codes: 0 rendered, 1 the map or a translation is unusable, 2 bad usage.
Stdlib only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _load_validator() -> Any:
    """Load the sibling validator as the single parser for this format.

    Loaded by file path rather than imported by name: this script is run
    directly (`python scripts/render_dashboard.py`), so `scripts/` is not a
    package on the path. Writing a second parser here was the alternative, and
    two parsers for one format drift apart by construction.
    """
    source = Path(__file__).resolve().parent / "validate_project_map.py"
    spec = importlib.util.spec_from_file_location("project_map_validator", source)
    if spec is None or spec.loader is None:
        raise SystemExit(f"error: cannot load {source.as_posix()}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_V = _load_validator()
LABEL_SPLIT: str = _V.LABEL_SPLIT
LABEL_RE = _V.LABEL_RE
SIGILS: str = _V.SIGILS
extract_graph = _V.extract_graph
parse_map = _V.parse_map

LANGS = ("en", "ko")

# UI chrome. Map content is authored by the user; only the frame is translated
# here. Keys must exist in both languages or the toggle would blank a label.
STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        "generated": "Generated from",
        "at": "at",
        "readonly": "Read-only. To change this page: change the code, update the map, re-run the renderer.",
        "nodes": "nodes",
        "edges": "edges",
        "withWhy": "carry 'why'",
        "pick": "Select a node in the diagram",
        "pickHint": "Scroll to zoom, drag to pan. Click a node for its full ledger entry.",
        "role": "Role",
        "paths": "Bound to",
        "noCode": "no code behind this node",
        "drill": "Open drill-down",
        "back": "Back",
        "root": "Root map",
        "legend": "Arrows mean <b>depends-on</b> unless labeled.",
        "sigEntry": "nothing depends on it — start here",
        "sigDrill": "has a drill-down map",
        "sigNoCode": "no code behind it",
        "reset": "Reset view",
        "noMermaid": "Mermaid could not be loaded from the CDN. The page needs network access once to draw the diagram; the ledger below still works.",
        "kind": "Diagram",
        "edgeSem": "Unlabeled edge",
        "INVARIANT": "Invariant",
        "CONSTRAINT": "Constraint",
        "REJECTED": "Rejected alternative",
        "CONTRACT": "Contract",
        "OWNER": "Owner",
        "whyEmpty": "No rationale recorded for this node yet.",
        "whyHint": "Invariants, constraints and rejected alternatives cannot be recovered from code.",
    },
    "ko": {
        "generated": "생성 원본",
        "at": "생성 시각",
        "readonly": "읽기 전용. 이 페이지를 바꾸려면 코드를 고치고, 지도를 갱신하고, 렌더러를 다시 실행하세요.",
        "nodes": "노드",
        "edges": "엣지",
        "withWhy": "개가 'why' 보유",
        "pick": "도표에서 노드를 선택하세요",
        "pickHint": "휠로 확대, 드래그로 이동. 노드를 클릭하면 원장 전체가 나옵니다.",
        "role": "역할",
        "paths": "바인딩",
        "noCode": "이 노드에는 코드가 없음",
        "drill": "드릴다운 열기",
        "back": "뒤로",
        "root": "최상위 지도",
        "legend": "라벨이 없는 화살표는 <b>depends-on</b> 을 뜻합니다.",
        "sigEntry": "아무도 의존하지 않음 — 여기서 시작",
        "sigDrill": "드릴다운 지도 보유",
        "sigNoCode": "코드 없음",
        "reset": "보기 초기화",
        "noMermaid": "CDN에서 Mermaid를 불러오지 못했습니다. 도표를 그리려면 한 번은 네트워크가 필요합니다. 아래 원장은 그대로 동작합니다.",
        "kind": "도표 종류",
        "edgeSem": "라벨 없는 엣지",
        "INVARIANT": "불변조건",
        "CONSTRAINT": "제약",
        "REJECTED": "기각된 대안",
        "CONTRACT": "계약",
        "OWNER": "담당",
        "whyEmpty": "이 노드에는 아직 근거가 기록되지 않았습니다.",
        "whyHint": "불변조건·제약·기각된 대안은 코드에서 복원할 수 없습니다.",
    },
}


def display_name(label: str, node_id: str) -> str:
    head = label.split(LABEL_SPLIT)[0].strip() if label else node_id
    while head and head[-1] in SIGILS:
        head = head[:-1].rstrip()
    return head or node_id


def read_map(path: Path) -> Tuple[Dict[str, Any], List[Path]]:
    """Turn one map file into the dashboard's data shape."""
    meta, _meta_lines, block, entries, diags = parse_map(path)
    fatal = [d for d in diags if d.level == "error"]
    if fatal:
        for d in fatal:
            print(d.render(), file=sys.stderr)
        raise SystemExit(1)

    kind = meta.get("kind", "flowchart")
    nodes, edges = extract_graph(kind, block)

    labels: Dict[str, str] = {}
    for _lineno, raw in block:
        for m in LABEL_RE.finditer(raw.split("%%", 1)[0]):
            labels.setdefault(m.group("id"), m.group("label"))

    incoming = {b for _, _, b, _ in edges}
    outgoing = {a for _, a, _, _ in edges}

    children: List[Path] = []
    out_nodes = []
    for node_id in nodes:
        entry = entries.get(node_id)
        if entry is None:
            continue
        record: Dict[str, Any] = {
            "id": node_id,
            "name": display_name(labels.get(node_id, ""), node_id),
            "role": entry.first("role") or "",
            "paths": [v for _, v in entry.values.get("path", [])],
            "entry": node_id not in incoming and node_id in (incoming | outgoing),
            "why": [],
        }
        owner = entry.first("OWNER")
        if owner:
            record["owner"] = owner
        child = entry.first("map")
        if child:
            record["map"] = child
            children.append(path.parent / child)
        why: List[Dict[str, str]] = []
        for key in ("INVARIANT", "CONSTRAINT", "CONTRACT", "REJECTED"):
            for _lineno, value in entry.values.get(key, []):
                why.append({"kind": key, "text": value})
        record["why"] = why
        out_nodes.append(record)

    data: Dict[str, Any] = {
        "file": path.name,
        "title": path.stem,
        "kind": kind,
        "edgeSemantics": meta.get("edges", ""),
        "mermaid": "\n".join(line for _lineno, line in block),
        "nodes": out_nodes,
        "edges": [{"a": a, "b": b, "label": label or ""} for _line, a, b, label in edges],
    }
    return data, children


def collect(root_map: Path) -> Dict[str, Dict[str, Any]]:
    """Read the root map and every drill-down it reaches, keyed by file name."""
    maps: Dict[str, Dict[str, Any]] = {}
    queue = [root_map]
    seen = set()
    while queue:
        current = queue.pop(0)
        resolved = current.resolve()
        if resolved in seen or not current.is_file():
            continue
        seen.add(resolved)
        data, children = read_map(current)
        maps[current.name] = data
        queue.extend(children)
    return maps


def translation_for(root_map: Path, lang: str) -> Optional[Path]:
    candidate = root_map.with_name(f"{root_map.stem}.{lang}{root_map.suffix}")
    return candidate if candidate.is_file() else None


def merge_translation(base: Dict[str, Dict[str, Any]], other: Dict[str, Dict[str, Any]], lang: str) -> List[str]:
    """Overlay translated role/why text onto the base maps. Returns problems."""
    problems: List[str] = []
    for filename, data in base.items():
        stem, _, suffix = filename.rpartition(".")
        translated_name = f"{stem}.{lang}.{suffix}"
        tr = other.get(translated_name) or other.get(filename)
        if tr is None:
            problems.append(f"{lang}: no translated map for `{filename}`")
            continue
        base_ids = {n["id"] for n in data["nodes"]}
        tr_ids = {n["id"] for n in tr["nodes"]}
        if base_ids != tr_ids:
            missing = sorted(base_ids - tr_ids)
            extra = sorted(tr_ids - base_ids)
            problems.append(
                f"{lang}: node ids differ in `{translated_name}`"
                + (f"; missing {missing}" if missing else "")
                + (f"; unexpected {extra}" if extra else "")
            )
            continue
        by_id = {n["id"]: n for n in tr["nodes"]}
        for node in data["nodes"]:
            source = by_id[node["id"]]
            node.setdefault("i18n", {})
            node["i18n"][lang] = {
                "name": source["name"],
                "role": source["role"],
                "why": source["why"],
                "owner": source.get("owner", ""),
            }
        # The translated map has its own diagram with translated labels and
        # subgraph titles. Switching language while the picture stays English
        # would leave the reader with two languages on one screen.
        data.setdefault("i18nMermaid", {})[lang] = tr["mermaid"]
    return problems


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — project map</title>
<style>
:root{
  --bg:#0d1117; --panel:#12181f; --line:#222c37; --fg:#e6edf3; --dim:#8b949e;
  --accent:#58a6ff; --warn:#d29922; --bad:#f85149; --ok:#3fb950;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.6 ui-sans-serif,system-ui,'Segoe UI','Malgun Gothic',sans-serif}
header{display:flex;align-items:center;gap:16px;padding:12px 18px;
  border-bottom:1px solid var(--line);background:var(--panel);flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:650}
.crumbs{display:flex;gap:6px;align-items:center;color:var(--dim);font-size:12px}
.crumbs button{background:none;border:none;color:var(--accent);cursor:pointer;
  font:inherit;padding:0;text-decoration:underline}
.spacer{flex:1}
.stats{color:var(--dim);font-size:12px}
.stats b{color:var(--fg);font-weight:600}
.langs{display:flex;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.langs button{background:none;border:none;color:var(--dim);padding:4px 12px;
  cursor:pointer;font:inherit;font-size:12px}
.langs button[aria-pressed=true]{background:var(--accent);color:#08131f;font-weight:650}
.banner{padding:7px 18px;background:#161b22;border-bottom:1px solid var(--line);
  color:var(--dim);font-size:12px;display:flex;gap:10px;flex-wrap:wrap}
.banner code{color:var(--fg)}
main{display:grid;grid-template-columns:1fr 380px;height:calc(100vh - 92px)}
#stage{position:relative;overflow:hidden;cursor:grab}
#stage.drag{cursor:grabbing}
#canvas{transform-origin:0 0;padding:26px}
#stage .err{position:absolute;inset:24px;color:var(--warn)}
.tools{position:absolute;right:12px;bottom:12px;display:flex;gap:6px}
.tools button{background:var(--panel);border:1px solid var(--line);color:var(--fg);
  border-radius:6px;padding:5px 10px;cursor:pointer;font:inherit;font-size:12px}
aside{border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:18px}
aside h2{font-size:15px;margin:0 0 2px}
aside .sub{color:var(--dim);font-size:12px;margin-bottom:14px}
.kv{margin:12px 0}
.kv .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.paths{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:12px;
  color:var(--fg);word-break:break-all}
.why{border-left:3px solid var(--line);padding:7px 0 7px 11px;margin:10px 0}
.why.INVARIANT{border-color:var(--ok)} .why.CONSTRAINT{border-color:var(--warn)}
.why.REJECTED{border-color:var(--bad)} .why.CONTRACT{border-color:var(--accent)}
.why .t{font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.empty{color:var(--dim);font-size:13px}
.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;
  padding:1px 9px;font-size:11px;color:var(--dim);margin-right:6px}
.legend{color:var(--dim);font-size:12px;padding:8px 18px;border-top:1px solid var(--line);
  background:var(--panel)}
.legend code{color:var(--fg)}
aside button.drill{margin-top:14px;background:var(--accent);color:#08131f;border:none;
  border-radius:6px;padding:7px 13px;font:inherit;font-weight:650;cursor:pointer}
g.node{cursor:pointer}
g.node.sel rect,g.node.sel polygon,g.node.sel circle,g.node.sel path{
  stroke:var(--accent)!important;stroke-width:3px!important}
</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
</head><body>
<header>
  <h1 id="title"></h1>
  <div class="crumbs" id="crumbs"></div>
  <div class="spacer"></div>
  <div class="stats" id="stats"></div>
  <div class="langs" id="langs"></div>
</header>
<div class="banner">
  <span><span id="lblGen"></span> <code>__SOURCE__</code></span>
  <span><span id="lblAt"></span> <code>__STAMP__</code></span>
  <span id="lblRo"></span>
</div>
<main>
  <div id="stage"><div id="canvas"></div>
    <div class="tools"><button id="reset"></button></div>
  </div>
  <aside id="panel"></aside>
</main>
<div class="legend" id="legend"></div>
<script>
const DATA = __DATA__;
const STRINGS = __STRINGS__;
const ROOT = __ROOT__;
let lang = "en", currentMap = ROOT, selected = null, stack = [];
let scale = 1, tx = 0, ty = 0;

const t = k => (STRINGS[lang] && STRINGS[lang][k]) || STRINGS.en[k] || k;
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

function nodeView(n){
  const tr = n.i18n && n.i18n[lang];
  return {
    id:n.id, entry:n.entry, map:n.map, paths:n.paths,
    name:(tr && tr.name) || n.name,
    role:(tr && tr.role) || n.role,
    owner:(tr && tr.owner) || n.owner || "",
    why:(tr && tr.why && tr.why.length) ? tr.why : n.why
  };
}

function applyTransform(){
  document.getElementById("canvas").style.transform =
    `translate(${tx}px,${ty}px) scale(${scale})`;
}

// Mermaid element ids look like `<render>-flowchart-<nodeId>-<n>`, and a node
// id may itself contain hyphens, so splitting on "-" picks the wrong token.
// Match against the ids we already know, longest first.
function nodeIdOf(g, m){
  const raw = g.id || "";
  const known = m.nodes.map(n => n.id).sort((a, b) => b.length - a.length);
  return known.find(id => raw.includes("-" + id + "-") || raw.endsWith("-" + id)) || null;
}

async function draw(keepView){
  const m = DATA[currentMap];
  const canvas = document.getElementById("canvas");
  const src = (m.i18nMermaid && m.i18nMermaid[lang]) || m.mermaid;
  if (typeof mermaid === "undefined"){
    canvas.innerHTML = `<div class="err">${esc(t("noMermaid"))}</div>`;
  } else {
    const { svg } = await mermaid.render("g" + Math.random().toString(36).slice(2), src);
    canvas.innerHTML = svg;
    for (const g of canvas.querySelectorAll("g.node")){
      const id = nodeIdOf(g, m);
      if (!id) continue;
      g.addEventListener("click", ev => { ev.stopPropagation(); select(id); });
    }
  }
  if (!keepView){ scale = 1; tx = 0; ty = 0; }
  applyTransform();
  chrome();
  select(keepView ? selected : null);
}

function chrome(){
  const m = DATA[currentMap];
  const withWhy = m.nodes.filter(n => nodeView(n).why.length).length;
  document.getElementById("title").textContent = m.title;
  document.getElementById("stats").innerHTML =
    `<b>${m.nodes.length}</b> ${esc(t("nodes"))} · <b>${m.edges.length}</b> ${esc(t("edges"))} · ` +
    `<b>${withWhy}</b> ${esc(t("withWhy"))} · ${esc(t("kind"))}: <b>${esc(m.kind)}</b>` +
    (m.edgeSemantics ? ` · ${esc(t("edgeSem"))}: <b>${esc(m.edgeSemantics)}</b>` : "");
  document.getElementById("lblGen").textContent = t("generated");
  document.getElementById("lblAt").textContent = t("at");
  document.getElementById("lblRo").textContent = t("readonly");
  document.getElementById("reset").textContent = t("reset");
  document.getElementById("legend").innerHTML =
    t("legend") + ` &nbsp;·&nbsp; <code>*</code> ${esc(t("sigEntry"))}` +
    ` &nbsp;·&nbsp; <code>+</code> ${esc(t("sigDrill"))}` +
    ` &nbsp;·&nbsp; <code>~</code> ${esc(t("sigNoCode"))}`;
  const crumbs = document.getElementById("crumbs");
  crumbs.innerHTML = "";
  if (stack.length){
    const b = document.createElement("button");
    b.textContent = "← " + t("back");
    b.onclick = () => { currentMap = stack.pop(); draw(); };
    crumbs.appendChild(b);
    const s = document.createElement("span");
    s.textContent = " " + DATA[currentMap].file;
    crumbs.appendChild(s);
  }
  const langs = document.getElementById("langs");
  langs.innerHTML = "";
  for (const code of Object.keys(STRINGS)){
    const b = document.createElement("button");
    b.textContent = code.toUpperCase();
    b.setAttribute("aria-pressed", String(code === lang));
    b.onclick = () => { lang = code; draw(true); };
    langs.appendChild(b);
  }
}

function select(id){
  selected = id;
  for (const g of document.querySelectorAll("g.node")) g.classList.remove("sel");
  const panel = document.getElementById("panel");
  const m = DATA[currentMap];
  const raw = m.nodes.find(n => n.id === id);
  if (!raw){
    panel.innerHTML = `<h2>${esc(t("pick"))}</h2><div class="sub">${esc(t("pickHint"))}</div>`;
    return;
  }
  for (const g of document.querySelectorAll("g.node"))
    if (nodeIdOf(g, m) === id) g.classList.add("sel");

  const n = nodeView(raw);
  const noCode = n.paths.length > 0 && n.paths.every(p => p === "-");
  let html = `<h2>${esc(n.name)}</h2><div class="sub">`;
  if (n.entry) html += `<span class="pill">*</span>`;
  if (n.map) html += `<span class="pill">+</span>`;
  if (noCode) html += `<span class="pill">~</span>`;
  html += `<code>${esc(n.id)}</code></div>`;
  html += `<div class="kv"><div class="k">${esc(t("role"))}</div><div>${esc(n.role)}</div></div>`;
  html += `<div class="kv"><div class="k">${esc(t("paths"))}</div><div class="paths">` +
    (noCode ? esc(t("noCode")) : n.paths.map(esc).join("<br>")) + `</div></div>`;
  if (n.owner)
    html += `<div class="kv"><div class="k">${esc(t("OWNER"))}</div><div>${esc(n.owner)}</div></div>`;
  if (n.why.length){
    for (const w of n.why)
      html += `<div class="why ${esc(w.kind)}"><div class="t">${esc(t(w.kind))}</div>${esc(w.text)}</div>`;
  } else {
    html += `<div class="empty">${esc(t("whyEmpty"))}<br>${esc(t("whyHint"))}</div>`;
  }
  if (n.map && DATA[n.map]){
    html += `<button class="drill" id="drill">${esc(t("drill"))} → ${esc(n.map)}</button>`;
  }
  panel.innerHTML = html;
  const d = document.getElementById("drill");
  if (d) d.onclick = () => { stack.push(currentMap); currentMap = n.map; draw(); };
}

const stage = document.getElementById("stage");
stage.addEventListener("wheel", e => {
  e.preventDefault();
  const r = stage.getBoundingClientRect();
  const mx = e.clientX - r.left, my = e.clientY - r.top;
  const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
  const next = Math.min(6, Math.max(0.25, scale * factor));
  tx = mx - (mx - tx) * (next / scale);
  ty = my - (my - ty) * (next / scale);
  scale = next; applyTransform();
}, { passive:false });

let dragging = false, ox = 0, oy = 0;
stage.addEventListener("mousedown", e => { dragging = true; ox = e.clientX - tx; oy = e.clientY - ty; stage.classList.add("drag"); });
addEventListener("mouseup", () => { dragging = false; stage.classList.remove("drag"); });
addEventListener("mousemove", e => { if (dragging){ tx = e.clientX - ox; ty = e.clientY - oy; applyTransform(); } });
stage.addEventListener("click", e => { if (e.target === stage || e.target.id === "canvas") select(null); });
document.getElementById("reset").onclick = () => { scale = 1; tx = 0; ty = 0; applyTransform(); };

if (typeof mermaid !== "undefined")
  mermaid.initialize({ startOnLoad:false, theme:"dark", securityLevel:"loose",
    flowchart:{ useMaxWidth:false, htmlLabels:true, curve:"basis", nodeSpacing:55, rankSpacing:70 },
    themeVariables:{ fontSize:"14px", fontFamily:"ui-sans-serif, Segoe UI, Malgun Gothic, sans-serif" } });
draw();
</script>
</body></html>
"""


def render(root_map: Path, out: Path) -> int:
    maps = collect(root_map)
    # Refuse to publish a map that does not validate. A dashboard makes a map
    # look authoritative; rendering a broken one dresses up rot as a product.
    root_dir = root_map.parent
    failures = [d for d in _V.validate(root_map, root_dir, set()) if d.level == "error"]
    for lang in LANGS:
        sibling = translation_for(root_map, lang)
        if sibling is not None:
            failures += [d for d in _V.validate(sibling, root_dir, set()) if d.level == "error"]
    if failures:
        for d in failures:
            print(d.render(), file=sys.stderr)
        print("\nFAILED: the map does not validate; fix it before rendering.", file=sys.stderr)
        return 1

    if not maps:
        print(f"error: {root_map.as_posix()}: nothing to render", file=sys.stderr)
        return 1

    problems: List[str] = []
    for lang in LANGS:
        if lang == "en":
            continue
        tr_root = translation_for(root_map, lang)
        if tr_root is None:
            continue
        tr_maps = collect(tr_root)
        problems.extend(merge_translation(maps, tr_maps, lang))

    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        print("\nFAILED: a translation disagrees with the map it translates.", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (
        TEMPLATE
        .replace("__TITLE__", root_map.stem)
        .replace("__SOURCE__", root_map.name)
        .replace("__STAMP__", stamp)
        .replace("__DATA__", json.dumps(maps, ensure_ascii=False))
        .replace("__STRINGS__", json.dumps(STRINGS, ensure_ascii=False))
        .replace("__ROOT__", json.dumps(root_map.name))
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    total_nodes = sum(len(m["nodes"]) for m in maps.values())
    translated = sum(1 for m in maps.values() for n in m["nodes"] if "i18n" in n)
    print(f"wrote {out.as_posix()}  ({len(maps)} map(s), {total_nodes} nodes, "
          f"{translated} translated, {out.stat().st_size // 1024} KB)")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render PROJECT.md into a read-only HTML dashboard.")
    ap.add_argument("map", nargs="?", default="PROJECT.md", help="root map file (default: PROJECT.md)")
    ap.add_argument("-o", "--out", default=None, help="output HTML (default: alongside the map)")
    ap.add_argument("--open", action="store_true", help="open the result in a browser")
    args = ap.parse_args(argv)

    root_map = Path(args.map)
    if not root_map.is_file():
        print(f"error: {root_map.as_posix()}: no such file", file=sys.stderr)
        return 2
    out = Path(args.out) if args.out else root_map.with_suffix(".html")

    code = render(root_map, out)
    if code == 0 and args.open:
        webbrowser.open(out.resolve().as_uri())
    return code


if __name__ == "__main__":
    sys.exit(main())
