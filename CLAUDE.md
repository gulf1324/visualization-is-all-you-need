# CLAUDE.md

Project-specific instructions. Structure and rationale live in `PROJECT.md` —
never restate them here.

## Project map

`PROJECT.md` is the structural source of truth: a Mermaid map plus a per-node
ledger of invariants, constraints, and rejected alternatives.

- Read `PROJECT.md` before exploring source or changing structure.
- A structural change (new/removed file with a responsibility, changed
  dependency, new external integration) is incomplete until `PROJECT.md` is
  updated in the same change.
- Validate: `python scripts/validate_project_map.py PROJECT.md`
- Audit against the real import graph: `python scripts/scan_structure.py --compare PROJECT.md`
- Both run in `.githooks/pre-commit`.

## What this repo is

A distributable Claude Code skill. The repo root **is** the skill package, so
`SKILL.md`, `references/`, `scripts/`, and `.claude-plugin/` must stay
installable by copy or by `npx skills add`.

## Rules specific to this repo

- `scripts/validate_project_map.py` is the canonical format definition. When a
  document disagrees with it, change the document or change both — never leave
  them in conflict. The format vocabulary appears in the validator constants,
  `references/spec.md`, `references/visual-encoding.md`, and `SKILL.md`; a
  vocabulary or sigil change touches all four.
- Scripts are **stdlib-only Python 3.8+**. A user must be able to run them with
  no install step. Never add a dependency, and never use 3.9+ syntax
  (`dict[str]`, `X | None`) in `scripts/` — the `typing` imports are
  deliberate, not legacy.
- Dogfood: this repo's own `PROJECT.md` is the first test of any format change.
  If a change makes the self-map awkward, the change is wrong.
- Commits follow Conventional Commits, enforced by `.githooks/commit-msg`.
  Versioning per `CONTRIBUTING.md`; `VERSION` is the single source of truth.
- Never claim the validator detects semantic drift. It verifies path existence,
  diagram↔ledger correspondence, and import-edge coverage — not whether a
  node's description still matches its code.
