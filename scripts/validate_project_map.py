#!/usr/bin/env python3
"""Validate a PROJECT.md project-map against the v1 format.

This script is the canonical definition of the format. `references/spec.md`
mirrors it for human readers; when the two disagree, this file wins.

Usage:
    python scripts/validate_project_map.py [PROJECT.md] [--strict] [--root DIR]

Exit codes:
    0  no errors (warnings may be present)
    1  at least one error, or --strict with at least one warning
    2  the map file could not be read

Stdlib only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

FORMAT_VERSION = "v1"

MARKER_RE = re.compile(r"<!--\s*project-map:\s*(v\d+)\s*-->")

# Diagram kind -> what it is allowed to describe. Closed vocabulary: an agent
# must be able to infer edge semantics from the kind alone.
DIAGRAM_KINDS: Dict[str, str] = {
    "flowchart": "structure / dependencies",
    "sequenceDiagram": "protocol / request lifecycle",
    "stateDiagram-v2": "lifecycle / state machine",
    "erDiagram": "data model",
    "C4Context": "system boundary",
}

# Ledger keys. Lowercase = mechanical metadata, UPPERCASE = the 'why' payload.
SINGLE_KEYS: Set[str] = {"role", "map", "OWNER"}
MULTI_KEYS: Set[str] = {"path", "INVARIANT", "CONSTRAINT", "REJECTED", "CONTRACT"}
LEDGER_KEYS: Set[str] = SINGLE_KEYS | MULTI_KEYS
WHY_KEYS: Set[str] = {"INVARIANT", "CONSTRAINT", "REJECTED", "CONTRACT"}
REQUIRED_KEYS: Tuple[str, ...] = ("role", "path")

SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
UNBOUND_PATH = "-"  # explicit "this node has no code" marker

NODE_WARN_LIMIT = 30  # above this a human stops reading the diagram

# Lines that open a construct but are not nodes.
NON_NODE_HEADS = {
    "subgraph", "end", "direction", "style", "classDef", "class", "click",
    "linkStyle", "accTitle", "accDescr", "note", "state", "title", "flowchart",
    "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2", "erDiagram",
    "C4Context", "participant", "actor", "activate", "deactivate", "autonumber",
    "loop", "alt", "else", "opt", "par", "and", "rect", "critical", "break",
    "UpdateLayoutConfig", "Enterprise_Boundary", "System_Boundary",
    "Container_Boundary", "Boundary", "Node_Boundary",
}

# A mermaid id may contain hyphens, but a trailing hyphen would swallow the
# first dash of an arrow: `api-v2-->store` must yield `api-v2`, not `api-v2--`.
ID = r"[A-Za-z_](?:[\w-]*[A-Za-z0-9_])?"

SUBGRAPH_RE = re.compile(r"^\s*subgraph\s+(?P<id>" + ID + r")")
FLOW_DEF_RE = re.compile(r"^\s*(?P<id>" + ID + r")\s*(?:\[|\(|\{|>)")
FLOW_INLINE_EDGE_RE = re.compile(
    r"(?P<a>" + ID + r")\s*--\s*(?P<label>[^>|\-][^>|]*?)\s*-->\s*(?P<b>" + ID + r")"
)
FLOW_EDGE_RE = re.compile(
    r"(?P<a>" + ID + r")\s*"
    r"(?:-{2,3}>|-{3}|-\.-+>|-\.-+|={2,3}>|={3}|--[xo]|x--|o--)\s*"
    r"(?:\|(?P<label>[^|]*)\|\s*)?"
    r"(?P<b>" + ID + r")"
)
SEQ_DECL_RE = re.compile(r"^\s*(?:participant|actor)\s+(?P<id>" + ID + r")")
SEQ_MSG_RE = re.compile(
    r"^\s*(?P<a>" + ID + r")\s*(?:-{1,2}>>?|-{1,2}[x)])\s*\+?-?\s*(?P<b>" + ID + r")\s*:"
)
STATE_DECL_RE = re.compile(r"^\s*state\s+(?:\"[^\"]*\"\s+as\s+)?(?P<id>" + ID + r")")
STATE_EDGE_RE = re.compile(
    r"(?P<a>\[\*\]|" + ID + r")\s*-->\s*(?P<b>\[\*\]|" + ID + r")"
)
ER_ENTITY_RE = re.compile(r"^\s*(?P<id>" + ID + r")\s*\{")
ER_REL_RE = re.compile(
    r"^\s*(?P<a>" + ID + r")\s+[|}{o][|}{o.\-]*\s+(?P<b>" + ID + r")\s*:"
)
C4_DECL_RE = re.compile(
    r"^\s*(?:Person|Person_Ext|System|System_Ext|SystemDb|SystemQueue|Container"
    r"|ContainerDb|ContainerQueue|Component|ComponentDb|Node)\w*\s*\(\s*"
    r"(?P<id>" + ID + r")"
)
# `Rel(...)`, `Rel_U(...)`, and the bidirectional `BiRel*(...)` forms.
C4_REL_RE = re.compile(
    r"^\s*(?:Bi)?Rel\w*\s*\(\s*(?P<a>" + ID + r")\s*,\s*(?P<b>" + ID + r")"
)


class Diag:
    __slots__ = ("level", "file", "line", "msg")

    def __init__(self, level: str, file: str, line: Optional[int], msg: str) -> None:
        self.level = level
        self.file = file
        self.line = line
        self.msg = msg

    def render(self) -> str:
        where = f"{self.file}:{self.line}" if self.line else self.file
        return f"{self.level}: {where}: {self.msg}"


class Entry:
    """One ledger entry: `### <slug>` plus its key/value lines."""

    __slots__ = ("slug", "line", "values")

    def __init__(self, slug: str, line: int) -> None:
        self.slug = slug
        self.line = line
        self.values: Dict[str, List[Tuple[int, str]]] = {}

    def add(self, key: str, line: int, value: str) -> None:
        self.values.setdefault(key, []).append((line, value))

    def first(self, key: str) -> Optional[str]:
        got = self.values.get(key)
        return got[0][1] if got else None

    def has_why(self) -> bool:
        return any(k in WHY_KEYS for k in self.values)


def strip_labels(line: str) -> str:
    """Remove bracketed labels and quoted text, keeping |edge labels| intact.

    `A[Parser] -->|calls| B[IR]` becomes `A -->|calls| B`, so endpoint ids can
    be matched without the label text interfering.
    """
    placeholders: List[str] = []

    def stash(m: "re.Match[str]") -> str:
        placeholders.append(m.group(1))
        return f"|\x00{len(placeholders) - 1}\x00|"

    line = re.sub(r"\|([^|]*)\|", stash, line)
    line = re.sub(r'"[^"]*"', '""', line)
    for pattern in (r"\[[^\[\]]*\]", r"\([^()]*\)", r"\{[^{}]*\}"):
        while True:
            new = re.sub(pattern, " ", line)
            if new == line:
                break
            line = new

    def restore(m: "re.Match[str]") -> str:
        return f"|{placeholders[int(m.group(1))]}|"

    return re.sub(r"\|\x00(\d+)\x00\|", restore, line)


def extract_graph(
    kind: str, block: Sequence[Tuple[int, str]]
) -> Tuple[Dict[str, int], List[Tuple[int, str, str, Optional[str]]]]:
    """Return ({node_id: first_line}, [(line, a, b, label)]) for a mermaid block.

    Only the documented subset of each diagram kind is recognized. Unrecognized
    constructs are ignored rather than reported: a false failure would train
    users to bypass the validator.
    """
    nodes: Dict[str, int] = {}
    edges: List[Tuple[int, str, str, Optional[str]]] = []
    # `subgraph core["core"] ... end` groups nodes; `core --> x` is legal and
    # means "this group depends on x". A container is not a node and must not
    # be required to carry a ledger entry.
    containers: Set[str] = set()

    def note(node_id: str, line: int) -> None:
        if node_id and node_id not in NON_NODE_HEADS:
            nodes.setdefault(node_id, line)

    for lineno, raw in block:
        line = raw.split("%%", 1)[0]
        if not line.strip():
            continue
        head = line.strip().split()[0].rstrip(":")

        if kind in ("flowchart", "graph"):
            sg = SUBGRAPH_RE.match(line)
            if sg:
                containers.add(sg.group("id"))
                continue
            m = FLOW_DEF_RE.match(line)
            if m and head not in NON_NODE_HEADS:
                note(m.group("id"), lineno)
            bare = strip_labels(line)
            consumed = []
            for m in FLOW_INLINE_EDGE_RE.finditer(bare):
                note(m.group("a"), lineno)
                note(m.group("b"), lineno)
                edges.append((lineno, m.group("a"), m.group("b"), m.group("label").strip()))
                consumed.append((m.start(), m.end()))
            if consumed:
                out, prev = [], 0
                for s, e in consumed:
                    out.append(bare[prev:s])
                    prev = e
                out.append(bare[prev:])
                bare = " ".join(out)
            for m in FLOW_EDGE_RE.finditer(bare):
                note(m.group("a"), lineno)
                note(m.group("b"), lineno)
                label = m.group("label")
                edges.append((lineno, m.group("a"), m.group("b"), label.strip() if label else None))

        elif kind == "sequenceDiagram":
            m = SEQ_DECL_RE.match(line)
            if m:
                note(m.group("id"), lineno)
                continue
            m = SEQ_MSG_RE.match(line)
            if m:
                note(m.group("a"), lineno)
                note(m.group("b"), lineno)
                edges.append((lineno, m.group("a"), m.group("b"), None))

        elif kind in ("stateDiagram-v2", "stateDiagram"):
            m = STATE_DECL_RE.match(line)
            if m:
                note(m.group("id"), lineno)
                continue
            for m in STATE_EDGE_RE.finditer(strip_labels(line)):
                a, b = m.group("a"), m.group("b")
                if a != "[*]":
                    note(a, lineno)
                if b != "[*]":
                    note(b, lineno)
                if a != "[*]" and b != "[*]":
                    edges.append((lineno, a, b, None))

        elif kind == "erDiagram":
            m = ER_ENTITY_RE.match(line)
            if m and head not in NON_NODE_HEADS:
                note(m.group("id"), lineno)
                continue
            m = ER_REL_RE.match(line)
            if m:
                note(m.group("a"), lineno)
                note(m.group("b"), lineno)
                edges.append((lineno, m.group("a"), m.group("b"), None))

        elif kind == "C4Context":
            m = C4_DECL_RE.match(line)
            if m:
                note(m.group("id"), lineno)
                continue
            m = C4_REL_RE.match(line)
            if m:
                note(m.group("a"), lineno)
                note(m.group("b"), lineno)
                edges.append((lineno, m.group("a"), m.group("b"), None))

    for container in containers:
        nodes.pop(container, None)
    return nodes, edges


def parse_map(path: Path) -> Tuple[Dict[str, str], Dict[str, int], List[Tuple[int, str]], Dict[str, Entry], List[Diag]]:
    """Split a map file into meta, marker, mermaid block and ledger entries."""
    name = path.as_posix()
    diags: List[Diag] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    marker_line = 0
    version = ""
    for i, line in enumerate(lines, start=1):
        m = MARKER_RE.search(line)
        if m:
            marker_line, version = i, m.group(1)
            break
    if not marker_line:
        diags.append(Diag("error", name, None, f"missing format marker `<!-- project-map: {FORMAT_VERSION} -->`"))
    elif version != FORMAT_VERSION:
        diags.append(Diag("error", name, marker_line, f"format {version} is not supported; this validator implements {FORMAT_VERSION}"))

    meta: Dict[str, str] = {}
    meta_lines: Dict[str, int] = {}
    block: List[Tuple[int, str]] = []
    entries: Dict[str, Entry] = {}

    section = ""
    in_fence = False
    fence_lang = ""
    fence_start = 0
    blocks_seen = 0
    current: Optional[Entry] = None
    last_key: Optional[str] = None

    for lineno, raw in enumerate(lines, start=1):
        fence = re.match(r"^\s*```+\s*(\w[\w+-]*)?\s*$", raw)
        if fence:
            if not in_fence:
                in_fence = True
                fence_lang = (fence.group(1) or "").lower()
                fence_start = lineno
                if fence_lang == "mermaid":
                    blocks_seen += 1
            else:
                in_fence = False
                fence_lang = ""
            continue
        if in_fence:
            if fence_lang == "mermaid" and blocks_seen == 1:
                block.append((lineno, raw))
            continue

        heading = re.match(r"^(#{2,3})\s+(.*\S)\s*$", raw)
        if heading:
            level, title = len(heading.group(1)), heading.group(2)
            if level == 2:
                section = title.strip().lower()
                current = None
            elif level == 3 and section == "nodes":
                slug = title.strip()
                if slug in entries:
                    diags.append(Diag("error", name, lineno, f'duplicate ledger entry "{slug}"'))
                    current = entries[slug]
                else:
                    current = Entry(slug, lineno)
                    entries[slug] = current
                last_key = None
            continue

        kv = re.match(r"^\s*-\s+(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<val>.*)$", raw)
        if section == "meta" and kv and current is None:
            key = kv.group("key").strip()
            meta[key] = kv.group("val").strip()
            meta_lines[key] = lineno
            continue
        if current is not None:
            if kv:
                key = kv.group("key")
                last_key = key
                current.add(key, lineno, kv.group("val").strip())
            elif last_key and raw.startswith(("  ", "\t")) and raw.strip():
                prev = current.values[last_key][-1]
                current.values[last_key][-1] = (prev[0], f"{prev[1]} {raw.strip()}")
            elif not raw.strip():
                last_key = None

    if blocks_seen == 0:
        diags.append(Diag("error", name, None, "no ```mermaid block found; a map file must contain exactly one"))
    elif blocks_seen > 1:
        diags.append(Diag("error", name, fence_start, f"{blocks_seen} mermaid blocks found; a map file must contain exactly one (split with `map:` drill-down instead)"))

    return meta, meta_lines, block, entries, diags


def validate(path: Path, root: Path, visited: Set[Path]) -> List[Diag]:
    name = path.as_posix()
    resolved = path.resolve()
    if resolved in visited:
        return []
    visited.add(resolved)

    try:
        meta, meta_lines, block, entries, diags = parse_map(path)
    except OSError as exc:
        return [Diag("error", name, None, f"cannot read map file: {exc}")]
    except UnicodeDecodeError as exc:
        return [Diag("error", name, None, f"map file is not valid UTF-8: {exc}")]

    kind = meta.get("kind", "")
    if not kind:
        diags.append(Diag("error", name, None, "`## Meta` is missing `- kind:`"))
    elif kind not in DIAGRAM_KINDS:
        diags.append(Diag("error", name, meta_lines.get("kind"), f'unknown kind "{kind}"; allowed: {", ".join(sorted(DIAGRAM_KINDS))}'))

    if not meta.get("edges"):
        diags.append(Diag("error", name, None, "`## Meta` is missing `- edges:` (unlabeled edge semantics must be declared)"))

    edge_kinds = {meta["edges"].strip()} if meta.get("edges") else set()
    if meta.get("edge-kinds"):
        edge_kinds |= {k.strip() for k in meta["edge-kinds"].split(",") if k.strip()}

    if block and kind in DIAGRAM_KINDS:
        declared = block[0][1].strip().split()[0] if block[0][1].strip() else ""
        expected = "graph" if kind == "flowchart" else kind
        if declared and declared not in (expected, kind, "flowchart", "graph") and kind in ("flowchart",):
            diags.append(Diag("error", name, block[0][0], f'mermaid block opens with "{declared}" but `kind:` is "{kind}"'))
        elif declared and kind not in ("flowchart",) and not declared.startswith(kind.split("-")[0]):
            diags.append(Diag("error", name, block[0][0], f'mermaid block opens with "{declared}" but `kind:` is "{kind}"'))

    nodes, edges = extract_graph(kind, block)

    for node_id, lineno in sorted(nodes.items(), key=lambda kv: kv[1]):
        if node_id not in entries:
            diags.append(Diag("error", name, lineno, f'node "{node_id}" appears in the diagram but has no `### {node_id}` ledger entry'))
    for slug, entry in entries.items():
        if slug not in nodes:
            diags.append(Diag("error", name, entry.line, f'ledger entry "{slug}" does not appear in the diagram'))
        if not SLUG_RE.match(slug):
            diags.append(Diag("error", name, entry.line, f'invalid node id "{slug}"; must match {SLUG_RE.pattern}'))

    # Edge-label vocabulary is only meaningful where labels denote a relation
    # kind. In sequence/state/ER diagrams a label is a message or trigger name.
    if kind == "flowchart":
        for lineno, a, b, label in edges:
            if label and label not in edge_kinds:
                diags.append(Diag("error", name, lineno, f'edge {a}->{b} is labeled "{label}", which is not in `edges:`/`edge-kinds:` ({", ".join(sorted(edge_kinds)) or "none declared"})'))

    children: List[Path] = []
    for slug, entry in entries.items():
        for key in entry.values:
            if key not in LEDGER_KEYS:
                lineno = entry.values[key][0][0]
                diags.append(Diag("error", name, lineno, f'unknown ledger key "{key}" on node "{slug}"; allowed: {", ".join(sorted(LEDGER_KEYS))}'))
        for key in SINGLE_KEYS:
            if len(entry.values.get(key, [])) > 1:
                diags.append(Diag("error", name, entry.values[key][1][0], f'`{key}:` may appear only once on node "{slug}"'))
        for key in REQUIRED_KEYS:
            if not entry.values.get(key):
                diags.append(Diag("error", name, entry.line, f'node "{slug}" is missing required `{key}:`'))

        for lineno, value in entry.values.get("path", []):
            if value == UNBOUND_PATH:
                continue
            if not value:
                diags.append(Diag("error", name, lineno, f'node "{slug}" has an empty `path:`; use `-` for a node with no code'))
                continue
            matches = glob.glob(str(root / value), recursive=True)
            if not matches:
                diags.append(Diag("error", name, lineno, f'node "{slug}" binds to `{value}`, which does not exist under {root.as_posix()}'))

        child = entry.first("map")
        if child:
            child_path = (path.parent / child).resolve()
            lineno = entry.values["map"][0][0]
            if not child_path.is_file():
                diags.append(Diag("error", name, lineno, f'node "{slug}" points at drill-down map `{child}`, which does not exist'))
            else:
                children.append(path.parent / child)

    if len(nodes) > NODE_WARN_LIMIT:
        diags.append(Diag("warn", name, None, f"{len(nodes)} nodes exceeds the {NODE_WARN_LIMIT}-node readability limit; split a subtree into a `map:` drill-down"))
    if entries and not any(e.has_why() for e in entries.values()):
        diags.append(Diag("warn", name, None, f"no node carries any of {', '.join(sorted(WHY_KEYS))}; this map records structure but no 'why', which is the part code cannot recover"))
    if kind == "flowchart" and nodes:
        connected = {a for _, a, _, _ in edges} | {b for _, _, b, _ in edges}
        for node_id, lineno in sorted(nodes.items(), key=lambda kv: kv[1]):
            if node_id not in connected:
                diags.append(Diag("warn", name, lineno, f'node "{node_id}" has no edges; an unconnected node teaches nothing about structure'))

    for child in children:
        diags.extend(validate(child, root, visited))

    if entries:
        covered = sum(1 for e in entries.values() if e.has_why())
        diags.append(Diag("info", name, None, f"{len(entries)} nodes, {len(edges)} edges, {covered}/{len(entries)} nodes carry 'why'"))

    return diags


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Validate a PROJECT.md project-map (format v1).")
    ap.add_argument("map", nargs="?", default="PROJECT.md", help="path to the root map file (default: PROJECT.md)")
    ap.add_argument("--root", default=None, help="directory that `path:` values are resolved against (default: the map file's directory)")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument("--quiet", action="store_true", help="print errors and warnings only, no info lines")
    args = ap.parse_args(argv)

    map_path = Path(args.map)
    if not map_path.is_file():
        print(f"error: {map_path.as_posix()}: no such file", file=sys.stderr)
        return 2
    root = Path(args.root) if args.root else map_path.parent
    if not root.is_dir():
        print(f"error: --root {root.as_posix()} is not a directory", file=sys.stderr)
        return 2

    diags = validate(map_path, root, set())
    order = {"error": 0, "warn": 1, "info": 2}
    for diag in sorted(diags, key=lambda d: (order[d.level], d.file, d.line or 0)):
        if diag.level == "info" and args.quiet:
            continue
        stream = sys.stderr if diag.level == "error" else sys.stdout
        print(diag.render(), file=stream)

    errors = sum(1 for d in diags if d.level == "error")
    warns = sum(1 for d in diags if d.level == "warn")
    if errors:
        print(f"\nFAILED: {errors} error(s), {warns} warning(s)", file=sys.stderr)
        return 1
    if warns and args.strict:
        print(f"\nFAILED (--strict): {warns} warning(s)", file=sys.stderr)
        return 1
    if not args.quiet:
        print(f"\nOK: 0 errors, {warns} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
