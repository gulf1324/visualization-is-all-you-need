# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
The authoritative current version is stored in `VERSION`.

## [Unreleased]

### Added

- Repository bootstrap: git init, ignore/attribute/editor rules, SemVer baseline,
  Conventional Commits message template and `commit-msg` hook.
- `project-map` skill package: `SKILL.md` operating procedure,
  `references/spec.md` (format v1), `references/diagram-vocabulary.md` (five
  diagram kinds), `references/workflows.md` (Init/Update/Read loops), and
  `.claude-plugin/` install manifests.
- `scripts/scan_structure.py`: derives the dependency graph from real imports
  (Python, TS/JS, Go, Rust). `--suggest` bootstraps a map; `--compare` reports
  `missing-edge` (blocking), `stale-edge`, `uncovered`, and map coverage
  percentage. Strictness is proportional to code: edges leaving a node with no
  parseable source are counted as `unverifiable` and never flagged, and a
  project with no parseable source is reported as not machine-verified.
- `scripts/validate_project_map.py`: canonical format v1 definition. Checks
  path rot, diagram↔ledger correspondence both ways, node id syntax, duplicate
  entries, closed ledger-key vocabulary, declared edge labels, drill-down
  targets, and the 30-node readability limit.
- `PROJECT.md`: this repo mapped in its own format (11 nodes, all carrying
  'why'), as the first dogfood test of any format change.
- `.githooks/pre-commit`: runs both scripts so map rot cannot land silently.
  Bypass with `PROJECT_MAP_SKIP=1` for deliberate WIP commits.
- `CLAUDE.md`: project-specific instructions plus the map entry rule.
- `LICENSE`: MIT, matching the `license` field already declared in
  `.claude-plugin/plugin.json`.
- `references/visual-encoding.md`: the diagram's legibility standard. Two-line
  labels (`name<br/>short role`), ASCII sigils `*` (start here), `+` (has a
  drill-down), `~` (no code), a legend restating edge semantics next to the
  picture, and layout-stability rules. Every signal is text because terminal
  renderers drop `classDef` colour and normalize shapes; colour and shape are
  enhancement only.
- Validator enforces the encoding: label line 2 must be how `role:` starts,
  `+`/`~` must agree with `map:`/`path: -`, `*` is rejected on a node that
  something depends on, and a bare id or missing role line warns.
- `--suggest` emits the encoding already applied — labels, entry sigils,
  shapes, `classDef`, and the legend — and its output validates unedited.

- `scripts/render_dashboard.py` + `references/dashboard.md`: a read-only HTML
  dashboard generated from the map. Wheel zoom and drag pan, click a node for
  its full ledger entry, drill-down navigation with a back link, and an EN/KO
  toggle. Read-only is structural — the page is a build product with no input
  element — and the renderer refuses to build a map that fails validation.
- Optional content translation through a `PROJECT.<lang>.md` sibling map with
  identical node ids; the renderer merges it and fails the build when the node
  id sets diverge. `PROJECT.ko.md` ships as this repo's Korean map.

### Fixed

- Node ids no longer swallow arrow dashes. `api-v2-->store` yielded the node
  `api-v2--`, and `api-->>-client` in a sequence diagram yielded `api-`; both
  produced phantom nodes and false "missing ledger entry" errors.
- A `subgraph` id used as an edge endpoint (`core --> b`, legal Mermaid) was
  treated as a node and demanded a ledger entry. Containers are now excluded
  from the node set in both scripts.
- File-to-node assignment now prefers the most specific `path:` pattern. With
  `core: src/**` and `db: src/store/`, ledger order decided the owner, so a
  real cross-node import was absorbed into one node and its edge vanished —
  the scanner then reported an evidenced edge as unproven, inverting the truth.
- C4 `BiRel*(...)` relationships are now recognized; previously only `Rel*`
  matched, so bidirectional edges were dropped.
- TypeScript/JavaScript path aliases (`compilerOptions.paths`) are now
  resolved. On a real Next.js app the scanner saw 22 of 183 internal imports
  and drew **zero** edges, because `@/lib/x` looked like an external package.
- JSONC comment stripping no longer destroys `tsconfig.json`. A regex treated
  the `/*` inside the alias pattern `"@/*"` as a block-comment opener and ate
  the rest of the file, silently yielding an empty alias table.
- `--suggest` binds each node to its grouping prefix. It used to emit the
  directory of one member file, producing bindings like
  `src/app/[country]/@sidebar/board/[slug]/[id]/` for a node covering all of
  `src/app/`. Root-level files now bind to the file, not `./`.
- `path:` values are resolved literally before being globbed, so Next.js route
  directories (`[country]`, `[slug]`) no longer read as glob character classes
  and report a correct binding as missing.
- An isolated node is no longer marked as an entry point. In-degree 0 is
  trivially true for a disconnected node, and "start reading here" pointing at
  a leaf that leads nowhere turned the `*` sigil into noise.
