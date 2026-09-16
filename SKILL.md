---
name: project-map
description: Builds and maintains PROJECT.md — a single Mermaid map of a codebase that a human reads as a diagram and an agent reads as text, with per-node 'why' (invariants, constraints, rejected alternatives) that code cannot recover. Use for "visualize this project", "map this codebase", "what is this repo's architecture", "why is it built this way", "update PROJECT.md", "I don't understand this codebase", or when starting work in an unfamiliar repository. Also triggered by Korean phrasing: "프로젝트 시각화해줘", "구조 파악해줘", "PROJECT.md 만들어줘", "이 코드베이스 이해가 안 돼".
---

# project-map — Operating Procedure

You maintain `PROJECT.md`: one artifact, two projections. The human reads the
rendered Mermaid diagram. You read the same file as text. Nothing is duplicated,
so nothing can desynchronize.

`references/spec.md` is the format. `references/diagram-vocabulary.md` picks the
diagram kind. `references/workflows.md` has the three loops.

Two scripts do the mechanical work — stdlib-only Python, no install step:

| Script | Use |
|---|---|
| `scripts/scan_structure.py --suggest` | derive candidate nodes and **evidence-backed edges** from the real import graph |
| `scripts/scan_structure.py --compare PROJECT.md` | audit an existing map: edges the code has and the map lacks, edges with no evidence, source files no node covers |
| `scripts/validate_project_map.py PROJECT.md` | canonical format check — path rot, diagram↔ledger mismatch, undeclared edge labels |

When a document and `validate_project_map.py` disagree, the validator wins.

## Invariant Principles

1. **Meaning lives in syntax, never in layout.** You cannot see the rendered
   diagram. If "left means upstream" or "top means entry point" is not written
   as an edge or a ledger line, that meaning does not exist for you. Never
   encode information in visual position.
2. **The diagram carries structure; the ledger carries 'why'.** Mermaid `%%`
   comments are stripped by every renderer, so a human never sees them — putting
   the 'why' there silently breaks the human half of the contract. Node labels
   stay short; the 'why' goes in the `## Nodes` ledger keyed by node id.
3. **Every node binds to a real path.** `path:` is what makes rot mechanically
   detectable. A node with no code is legal but must say so with `path: -`.
4. **Draw edges from evidence, not from belief.** Your impression of "what
   depends on what" is a guess; an import is proof. Run the scanner and start
   from its edges. Where a real relationship is not an import (a spawn, an HTTP
   call, a queue write), draw it and say in `role:` how you verified it.
5. **A wrong map is worse than no map.** It misleads the human and poisons your
   own context. An unverifiable relationship gets said in words, not drawn as a
   confident arrow.
6. **Never let the map exceed what a human can hold.** Above 30 nodes,
   comprehension goes negative. Split into `map:` drill-downs instead.
7. **`REJECTED` is the highest-value line in the file.** Structure can be
   re-derived from code; a decision that was considered and rejected cannot.
   Record it whenever the user reveals one.

## Workflow selection

| Situation | Loop |
|---|---|
| No `PROJECT.md` exists | **Init** — read `references/workflows.md` §Init |
| Structure changed in this session | **Update** — §Update |
| Starting work in a mapped repo | **Read** — §Read |

## Init (condensed)

1. Establish the project's nature before drawing anything — a state machine
   drawn as a dependency graph is worse than no diagram. Pick the kind from
   `references/diagram-vocabulary.md`.
2. Run `python scripts/scan_structure.py --suggest` first. It gives you the
   import graph and a candidate grouping — a factual starting point instead of
   a guess. Then correct it: the scanner groups by directory, and a map groups
   by responsibility, which is not the same thing. Merge any node you cannot
   describe in one line.
3. Draft ≤30 nodes. If the project is larger, the root map holds domains and
   each domain gets a `map:` drill-down.
4. Write the ledger. `role:` and `path:` for every node — those are mechanical.
   Then ask the user for the 'why' you cannot infer: **which constraints are
   load-bearing, and what was tried and rejected.** This is the one part of the
   map that must come from a human.
5. Validate: `python scripts/validate_project_map.py PROJECT.md`. Do not
   present the map to the user until it exits 0.
6. Add the entry rule to `CLAUDE.md` (see `references/workflows.md` §Wiring) so
   future sessions actually load the map.

## Update (condensed)

This is the loop that matters. A map that is not updated is not a slightly
worse map; it is an active liability, because both the human and you will trust
it. Treat it exactly like `CLAUDE.md`: it is maintained continuously, not
written once.

Triggered by a new module, a deleted module, a changed dependency, a new
external integration, or a decision the user just stated.

1. `python scripts/scan_structure.py --compare PROJECT.md` — this tells you
   what actually drifted instead of relying on your memory of the session.
   `missing-edge` means the code grew a dependency the map does not show;
   `uncovered` means new code belongs to no node.
2. Edit only the affected nodes. Rebind `path:` for moved code.
3. Re-run `--compare` and the validator. Both clean, or the change is unfinished.

Record the user's decisions as `CONSTRAINT`/`REJECTED` at the moment they are
made. A rationale not written down in the session it was spoken is lost.

## Read (condensed)

Read `PROJECT.md` **before** exploring source. It is the cheap projection: a
few thousand tokens instead of dozens of file reads. Then open only the paths
the relevant nodes name. If the map contradicts the code, the map is stale —
fix it in the same session and tell the user what was wrong.

## Honest limits — state these; never overclaim

- `path:` existence is verifiable. Whether a node's description still *matches*
  the code behind it is not. The validator catches deleted and renamed code, not
  semantic drift.
- The validator recognizes the documented Mermaid subset. Exotic syntax is
  ignored rather than rejected, so an unparsed construct is silently unchecked.
- The scanner resolves Python, TS/JS, Go, and Rust imports. Other languages
  produce no edges — say so instead of implying the map was verified. Dynamic
  imports, DI containers, and runtime wiring are invisible to it.
- `stale-edge` is a report, not a verdict. Spawns, HTTP calls, and queue writes
  are real relationships with no import to prove them.
- Mermaid auto-layout means adding a node can reshuffle the whole picture and
  invalidate the human's spatial memory. Prefer small, additive edits.

## Reporting format

Every map change reports: ① nodes added/removed/rebound ② the validator's exact
output ③ which 'why' lines came from the user versus inferred by you ④ what you
could not determine and why.
