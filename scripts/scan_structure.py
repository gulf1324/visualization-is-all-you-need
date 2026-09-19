#!/usr/bin/env python3
"""Extract a project's real dependency structure from source, and compare it
to PROJECT.md.

This is what makes a map *accurate* instead of plausible. An agent's belief
about "what depends on what" is a guess; an import graph is evidence.

Two modes:

    # propose nodes and edges for a project that has no map yet
    python scripts/scan_structure.py --suggest [--depth 2] [--root .]

    # audit an existing map against the code
    python scripts/scan_structure.py --compare PROJECT.md [--root .]

`--compare` reports three kinds of drift:

    missing-edge  code imports across nodes that the map does not draw
    stale-edge    an edge the map draws with no import evidence
    uncovered     source files that belong to no node (map coverage gap)

Exit codes:
    0  no drift (or --suggest completed)
    1  drift found
    2  bad invocation

Stdlib only. Python 3.8+.
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build", "out",
    "target", ".next", ".turbo", "coverage", ".idea", ".vscode", "vendor",
    ".tmp", "tmp",
}

PY_EXT = {".py"}
JS_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts"}
GO_EXT = {".go"}
RS_EXT = {".rs"}
SOURCE_EXT = PY_EXT | JS_EXT | GO_EXT | RS_EXT

JS_RESOLVE_ORDER = (
    "", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts",
    "/index.ts", "/index.tsx", "/index.js", "/index.jsx", "/index.mjs",
)

PY_IMPORT_RE = re.compile(
    r"^\s*(?:from\s+(?P<from>\.*[\w.]*)\s+import|import\s+(?P<plain>[\w.]+(?:\s*,\s*[\w.]+)*))",
    re.MULTILINE,
)
JS_IMPORT_RE = re.compile(
    r"""(?:from\s*|require\s*\(\s*|import\s*\(\s*|import\s+)['"](?P<spec>[^'"]+)['"]""")
GO_IMPORT_RE = re.compile(r"""^\s*(?:import\s+)?(?:[\w.]+\s+)?"(?P<spec>[^"]+)"\s*$""", re.MULTILINE)
GO_MODULE_RE = re.compile(r"^\s*module\s+(?P<mod>\S+)", re.MULTILINE)
RS_MOD_RE = re.compile(r"^\s*(?:pub\s+)?mod\s+(?P<name>\w+)\s*;", re.MULTILINE)
RS_USE_RE = re.compile(r"^\s*(?:pub\s+)?use\s+crate::(?P<path>[\w:]+)", re.MULTILINE)


def iter_sources(root: Path) -> Iterable[Path]:
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            children = list(current.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir():
                if child.name not in SKIP_DIRS and not child.name.startswith(".git"):
                    stack.append(child)
            elif child.suffix in SOURCE_EXT:
                yield child


def rel(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def strip_jsonc(text: str) -> str:
    """Remove JSONC comments and trailing commas without touching strings.

    A regex cannot do this: the most common alias pattern is `"@/*"`, whose
    `/*` reads as the start of a block comment and swallows the rest of the
    file. That silently produced an empty alias table, which in turn made every
    Next.js project look edgeless.
    """
    out: List[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def load_ts_aliases(root: Path) -> List[Tuple[str, List[Path]]]:
    """Read `compilerOptions.paths` from tsconfig.json.

    Without this, a Next.js or monorepo codebase looks edgeless: `@/lib/db` is
    not a relative specifier, so it would be dismissed as an external package.
    On a real Next.js app that is the overwhelming majority of internal imports,
    and the map would come out as disconnected boxes.
    """
    aliases: List[Tuple[str, List[Path]]] = []
    config = root / "tsconfig.json"
    if not config.is_file():
        config = root / "jsconfig.json"
        if not config.is_file():
            return aliases
    try:
        text = config.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return aliases
    text = strip_jsonc(text)
    try:
        data = json.loads(text)
    except ValueError:
        return aliases
    options = data.get("compilerOptions") or {}
    base = (root / (options.get("baseUrl") or ".")).resolve()
    for pattern, targets in (options.get("paths") or {}).items():
        if not isinstance(targets, list):
            continue
        prefix = pattern[:-1] if pattern.endswith("*") else pattern
        resolved = [
            (base / (t[:-1] if t.endswith("*") else t)).resolve()
            for t in targets if isinstance(t, str)
        ]
        if resolved:
            aliases.append((prefix, resolved))
    # Longest prefix wins, so `@/lib/` beats `@/`.
    aliases.sort(key=lambda kv: -len(kv[0]))
    return aliases


def resolve_js(origin: Path, spec: str, aliases: Sequence[Tuple[str, List[Path]]] = ()) -> Optional[Path]:
    bases: List[Path] = []
    if spec.startswith("."):
        bases.append((origin.parent / spec).resolve())
    else:
        for prefix, targets in aliases:
            if spec.startswith(prefix):
                tail = spec[len(prefix):]
                bases.extend((target / tail).resolve() if tail else target for target in targets)
                break
        if not bases:
            return None  # bare specifier: a package, not an internal edge
    for base in bases:
        for suffix in JS_RESOLVE_ORDER:
            candidate = Path(str(base) + suffix)
            if candidate.is_file():
                return candidate
    return None


def resolve_py(root: Path, origin: Path, module: str, level: int) -> Optional[Path]:
    parts = [p for p in module.split(".") if p]
    if level:
        anchor = origin.parent
        for _ in range(level - 1):
            anchor = anchor.parent
        bases = [anchor]
    else:
        bases = [root]
        # also try the importing file's package roots, for src-layout projects
        cursor = origin.parent
        while cursor != root and root in cursor.parents:
            bases.append(cursor)
            cursor = cursor.parent
    for base in bases:
        target = base.joinpath(*parts) if parts else base
        for candidate in (target.with_suffix(".py"), target / "__init__.py"):
            if candidate.is_file():
                return candidate
    return None


def resolve_go(root: Path, module_prefix: Optional[str], spec: str) -> Optional[Path]:
    if not module_prefix or not spec.startswith(module_prefix):
        return None
    tail = spec[len(module_prefix):].strip("/")
    target = root / tail if tail else root
    if target.is_dir():
        for child in sorted(target.glob("*.go")):
            return child
    return None


def resolve_rs(origin: Path, name: str) -> Optional[Path]:
    for candidate in (origin.parent / f"{name}.rs", origin.parent / name / "mod.rs"):
        if candidate.is_file():
            return candidate
    return None


def build_file_graph(root: Path) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    """Return (source files, [(importer, imported, evidence)]) as repo-relative paths."""
    files = sorted(iter_sources(root))
    module_prefix = None
    gomod = root / "go.mod"
    if gomod.is_file():
        found = GO_MODULE_RE.search(gomod.read_text(encoding="utf-8", errors="replace"))
        module_prefix = found.group("mod") if found else None
    ts_aliases = load_ts_aliases(root)

    edges: List[Tuple[str, str, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ext = path.suffix
        targets: List[Tuple[Optional[Path], str]] = []

        if ext in PY_EXT:
            for m in PY_IMPORT_RE.finditer(text):
                raw = m.group("from")
                if raw is not None:
                    level = len(raw) - len(raw.lstrip("."))
                    targets.append((resolve_py(root, path, raw.lstrip("."), level), raw or "."))
                else:
                    for name in (m.group("plain") or "").split(","):
                        name = name.strip()
                        if name:
                            targets.append((resolve_py(root, path, name, 0), name))
        elif ext in JS_EXT:
            for m in JS_IMPORT_RE.finditer(text):
                spec = m.group("spec")
                targets.append((resolve_js(path, spec, ts_aliases), spec))
        elif ext in GO_EXT:
            for m in GO_IMPORT_RE.finditer(text):
                spec = m.group("spec")
                targets.append((resolve_go(root, module_prefix, spec), spec))
        elif ext in RS_EXT:
            for m in RS_MOD_RE.finditer(text):
                name = m.group("name")
                targets.append((resolve_rs(path, name), f"mod {name}"))
            for m in RS_USE_RE.finditer(text):
                head = m.group("path").split("::")[0]
                targets.append((resolve_rs(path, head), f"crate::{head}"))

        origin = rel(root, path)
        for resolved, spec in targets:
            if resolved is None:
                continue
            target = rel(root, resolved)
            if target != origin:
                edges.append((origin, target, spec))
    return [rel(root, f) for f in files], edges


def group_by_depth(files: Sequence[str], depth: int) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Map each file to a candidate node id, and each node id to its `path:`.

    The path must come from the grouping prefix, not from one member file's
    directory: taking `dirname(files[0])` produced bindings like
    `src/app/[country]/@sidebar/board/[slug]/[id]/` for a node that actually
    covers all of `src/app/`.
    """
    assign: Dict[str, str] = {}
    paths: Dict[str, str] = {}
    for f in files:
        parts = f.split("/")
        if len(parts) > depth:
            prefix = parts[:depth]
            location = "/".join(prefix) + "/"
        elif len(parts) > 1:
            prefix = parts[:-1]
            location = "/".join(prefix) + "/"
        else:
            # A file at the project root is its own node, bound to the file.
            prefix = [parts[0]]
            location = parts[0]
        slug = "_".join(prefix) if prefix else "root"
        slug = re.sub(r"[^a-z0-9_-]+", "_", slug.lower()).strip("_") or "root"
        if not re.match(r"^[a-z]", slug):
            slug = f"n_{slug}"
        assign[f] = slug
        paths.setdefault(slug, location)
    return assign, paths


def parse_map_nodes(map_path: Path) -> Tuple[Dict[str, List[str]], Set[Tuple[str, str]], List[str]]:
    """Return ({node: [path globs]}, {(a, b) edges}, problems)."""
    problems: List[str] = []
    text = map_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    nodes: Dict[str, List[str]] = {}
    edges: Set[Tuple[str, str]] = set()
    section = ""
    current = ""
    in_mermaid = False

    # Trailing hyphens must not swallow arrow dashes: `api-v2-->store`.
    ident = r"[A-Za-z_](?:[\w-]*[A-Za-z0-9_])?"
    arrow = re.compile(
        r"(?P<a>" + ident + r")\s*(?:-{2,3}>|-{3}|-\.-+>|={2,3}>|--[xo])\s*"
        r"(?:\|[^|]*\|\s*)?(?P<b>" + ident + r")"
    )
    inline = re.compile(r"(?P<a>" + ident + r")\s*--\s*[^>|]+?\s*-->\s*(?P<b>" + ident + r")")
    subgraph = re.compile(r"^\s*subgraph\s+(?P<id>" + ident + r")")
    containers: Set[str] = set()

    for raw in lines:
        fence = re.match(r"^\s*```+\s*(\w+)?\s*$", raw)
        if fence:
            in_mermaid = (fence.group(1) or "").lower() == "mermaid" and not in_mermaid
            continue
        if in_mermaid:
            line = raw.split("%%", 1)[0]
            sg = subgraph.match(line)
            if sg:
                containers.add(sg.group("id"))
                continue
            for pattern in (r'"[^"]*"', r"\[[^\[\]]*\]", r"\([^()]*\)", r"\{[^{}]*\}"):
                while True:
                    new = re.sub(pattern, " ", line)
                    if new == line:
                        break
                    line = new
            for m in inline.finditer(line):
                edges.add((m.group("a"), m.group("b")))
            for m in arrow.finditer(line):
                edges.add((m.group("a"), m.group("b")))
            continue
        heading = re.match(r"^(#{2,3})\s+(.*\S)\s*$", raw)
        if heading:
            if len(heading.group(1)) == 2:
                section = heading.group(2).strip().lower()
                current = ""
            elif section == "nodes":
                current = heading.group(2).strip()
                nodes.setdefault(current, [])
            continue
        kv = re.match(r"^\s*-\s+path\s*:\s*(?P<val>.*\S)\s*$", raw)
        if kv and current:
            nodes[current].append(kv.group("val").strip())

    # A subgraph is a container, not a node; edges touching one are not
    # node-to-node relationships the import graph can be compared against.
    edges = {(a, b) for a, b in edges if a not in containers and b not in containers}

    if not nodes:
        problems.append("no `## Nodes` ledger entries found")
    return nodes, edges, problems


def resolve_binding(root: Path, pattern: str) -> List[str]:
    """Resolve a `path:` value, treating it as a literal before a glob.

    Next.js route directories are named `[country]`, `[slug]`, `[id]`. To
    `glob` those brackets are character classes, so a literal directory named
    `[country]` never matches itself and the binding looks broken. Try the
    literal path first; fall back to globbing only when it does not exist.
    """
    literal = root / pattern
    if literal.exists():
        return [str(literal)]
    return globmod.glob(str(literal), recursive=True)


def pattern_specificity(pattern: str) -> int:
    """How precisely a `path:` pattern names a location.

    Nested nodes are normal: `core` may claim `src/**` while `db` claims
    `src/store/`. Whoever is written first in the ledger must not win, or a
    real cross-node import gets absorbed into one node and the edge silently
    disappears — the scanner would then report an evidenced edge as unproven,
    inverting the truth. The more specific pattern owns the file.
    """
    literal = re.split(r"[*?\[]", pattern, maxsplit=1)[0]
    return len([seg for seg in literal.strip("/").split("/") if seg])


def assign_by_map(root: Path, files: Sequence[str], nodes: Dict[str, List[str]]) -> Tuple[Dict[str, str], List[Tuple[str, str, str]]]:
    """Map files to nodes via `path:` globs, most specific pattern winning.

    Returns (file->node, conflicts). A conflict is reported only when two
    nodes claim a file with equal specificity — a genuinely ambiguous boundary.
    """
    best: Dict[str, Tuple[int, str]] = {}
    conflicts: List[Tuple[str, str, str]] = []
    file_set = set(files)
    for node, patterns in nodes.items():
        for pattern in patterns:
            if pattern == "-":
                continue
            score = pattern_specificity(pattern)
            for hit in resolve_binding(root, pattern):
                path = Path(hit)
                if path.is_dir():
                    members = list(iter_sources(path))
                else:
                    members = [path] if path.suffix in SOURCE_EXT else []
                for member in members:
                    key = rel(root, member)
                    if key not in file_set:
                        continue
                    prior = best.get(key)
                    if prior is None or score > prior[0]:
                        best[key] = (score, node)
                    elif score == prior[0] and prior[1] != node:
                        conflicts.append((key, prior[1], node))
    return {k: v[1] for k, v in best.items()}, conflicts


def collapse(edges: Sequence[Tuple[str, str, str]], assign: Dict[str, str]) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """File edges -> node edges, keeping one piece of evidence per node edge."""
    out: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for importer, imported, spec in edges:
        a, b = assign.get(importer), assign.get(imported)
        if not a or not b or a == b:
            continue
        out.setdefault((a, b), (importer, imported))
    return out


def cmd_suggest(root: Path, depth: int) -> int:
    files, file_edges = build_file_graph(root)
    if not files:
        print(f"no source files found under {root.as_posix()} "
              f"(recognized: {', '.join(sorted(SOURCE_EXT))})", file=sys.stderr)
        return 1
    assign, locations = group_by_depth(files, depth)
    node_edges = collapse(file_edges, assign)
    members: Dict[str, List[str]] = {}
    for f, node in assign.items():
        members.setdefault(node, []).append(f)

    # Emit the skeleton already carrying the visual encoding. If the generator
    # produced bare ids, every user would have to add labels and sigils by
    # hand, and a standard that costs manual effort on every node does not get
    # followed. The placeholder role is deliberately identical in label and
    # ledger so the map validates as-is.
    # An entry point is a node nothing depends on *that participates in the
    # graph*. An isolated node (a stray root-level config file) satisfies
    # in-degree 0 trivially; marking it `*` tells the reader to start at a leaf
    # that leads nowhere, and with several of them the sigil becomes noise.
    incoming = {b for _, b in node_edges}
    connected = incoming | {a for a, _ in node_edges}
    entries = [n for n in sorted(members) if n not in incoming and n in connected]
    placeholder = "TODO describe this"

    print(f"# scanned {len(files)} source files, {len(file_edges)} internal imports, "
          f"{len(members)} candidate nodes at depth {depth}\n")
    print("```mermaid")
    print("flowchart TD")
    for node in sorted(members):
        mark = " *" if node in entries else ""
        shape = ("([", "])") if node in entries else ("[", "]")
        print(f'  {node}{shape[0]}"{node}{mark}<br/>{placeholder}"{shape[1]}')
    for (a, b), _evidence in sorted(node_edges.items()):
        print(f"  {a} --> {b}")
    if entries:
        print("  classDef entry fill:#1f6feb,stroke:#58a6ff,color:#ffffff")
        print(f"  class {','.join(entries)} entry")
    print("```\n")
    print("Arrows mean **depends-on** unless labeled.")
    print("`*` nothing depends on it — start reading here · "
          "`+` has a drill-down map · `~` no code behind it.\n")
    print("## Nodes\n")
    for node in sorted(members):
        count = len(members[node])
        shared = locations.get(node, ".")
        print(f"### {node}")
        print(f"- role: {placeholder} — responsibility of these {count} file(s)")
        print(f"- path: {shared}")
        print()
    print("# Candidate only. Verify every node and edge, merge nodes you cannot")
    print("# describe in one line, replace every TODO in both the label and the")
    print("# ledger (they must agree), then add INVARIANT/CONSTRAINT/REJECTED")
    print("# from the user.")
    if len(members) > 30:
        print(f"# warn: {len(members)} nodes exceeds the 30-node readability limit; "
              f"re-run with --depth 1 or plan drill-downs")
    return 0


def cmd_compare(root: Path, map_path: Path, quiet: bool = False) -> int:
    files, file_edges = build_file_graph(root)
    nodes, map_edges, problems = parse_map_nodes(map_path)
    for problem in problems:
        print(f"error: {map_path.as_posix()}: {problem}", file=sys.stderr)
    if problems:
        return 1

    assign, conflicts = assign_by_map(root, files, nodes)
    code_edges = collapse(file_edges, assign)

    missing = sorted(set(code_edges) - map_edges)
    uncovered = sorted(f for f in files if f not in assign)

    # A node whose `path:` holds no parseable source cannot originate a
    # provable edge — a markdown file has no imports. Demanding proof there
    # produces a permanent wall of findings, and a report that is always noisy
    # trains the reader to skip it, which is how a real error later hides in
    # the list. So: only edges leaving a node with parseable source are held to
    # the import standard. Strictness is for code; the rest is reported as
    # unverifiable and not counted.
    code_nodes = set(assign.values())
    stale: List[Tuple[str, str]] = []
    unverifiable: List[Tuple[str, str]] = []
    for a, b in sorted(map_edges - set(code_edges)):
        if a not in nodes or b not in nodes:
            continue
        (stale if a in code_nodes else unverifiable).append((a, b))

    for f, first, second in sorted(conflicts):
        print(f"warn: {f} is claimed by both `{first}` and `{second}`; "
              f"node boundaries overlap", file=sys.stdout)

    for a, b in missing:
        src, dst = code_edges[(a, b)]
        print(f"missing-edge: {a} -> {b}  (evidence: {src} imports {dst})", file=sys.stderr)

    # `stale-edge` and `uncovered` are advisory. In a hook they are pure noise
    # on every commit, and a noisy gate is a gate that gets disabled.
    if not quiet:
        for a, b in stale:
            print(f"stale-edge: {a} -> {b}  (node `{a}` has source, but no import proves this edge)",
                  file=sys.stdout)

        if uncovered:
            shown = uncovered[:10]
            for f in shown:
                print(f"uncovered: {f} belongs to no node", file=sys.stdout)
            if len(uncovered) > len(shown):
                print(f"uncovered: ... and {len(uncovered) - len(shown)} more", file=sys.stdout)

    covered = len(files) - len(uncovered)
    pct = (100.0 * covered / len(files)) if files else 100.0
    print(f"\ncoverage: {covered}/{len(files)} source files mapped ({pct:.0f}%)")
    print(f"edges: {len(code_edges)} in code, {len(map_edges)} in map, "
          f"{len(missing)} missing, {len(stale)} unverified, "
          f"{len(unverifiable)} unverifiable")
    if unverifiable:
        print(f"note: {len(unverifiable)} edge(s) leave a node with no parseable source "
              f"(docs, config, shell); those are not held to the import standard")
    if not files:
        print("note: no parseable source found — this map's structure is NOT "
              "machine-verified. Say so rather than implying it was checked.")

    if missing:
        print(f"\nFAILED: {len(missing)} import edge(s) exist in code but not in the map", file=sys.stderr)
        return 1
    print("\nOK: every cross-node import in the code is drawn in the map")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Extract real project structure and audit PROJECT.md against it.")
    ap.add_argument("--root", default=".", help="project root to scan (default: .)")
    ap.add_argument("--suggest", action="store_true", help="propose candidate nodes and edges")
    ap.add_argument("--depth", type=int, default=2, help="directory depth for candidate grouping (default: 2)")
    ap.add_argument("--compare", metavar="MAP", help="audit this map file against the code")
    ap.add_argument("--quiet", action="store_true", help="with --compare: print only blocking findings and the summary")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"error: --root {root.as_posix()} is not a directory", file=sys.stderr)
        return 2
    if bool(args.suggest) == bool(args.compare):
        print("error: pass exactly one of --suggest or --compare MAP", file=sys.stderr)
        return 2
    if args.compare:
        map_path = Path(args.compare)
        if not map_path.is_file():
            print(f"error: {map_path.as_posix()}: no such file", file=sys.stderr)
            return 2
        return cmd_compare(root, map_path, quiet=args.quiet)
    if args.depth < 1:
        print("error: --depth must be >= 1", file=sys.stderr)
        return 2
    return cmd_suggest(root, args.depth)


if __name__ == "__main__":
    sys.exit(main())
