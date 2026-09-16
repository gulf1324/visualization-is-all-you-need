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
