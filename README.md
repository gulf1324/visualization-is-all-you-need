# Insights
## The era of agentic coding has arrived.
---
### Some optimists say 
> "the bottleneck is the human review.", 
### While on the other side, they say 
> "there's no way a black-box-software-factory is happening."

## This takes all have in common, which is "if humans and agents communicate with each other smoothly, it will be OKAY."

### And the link to that comes down to 'visualization'. 

> _Throughout the history, drawings and diagrams has been always better abstracting informaations and meanings than the texts._

### From small personalized program to huge corporate ERP, the structural visulization can be done, and it's worth it. This way, humans can order agents while having control and understanding it fully at the same time. Even to the detailed levels of the system. 

### And also for the agents, it doesn't need to waste ton of fixed tokens each session, but to just ingest a single diagram with full of useful informations. 

---

# `project-map` — the skill

This repo **is** the skill package. One artifact, `PROJECT.md`, with two
projections: the human reads the rendered Mermaid diagram, the agent reads the
same file as text. Nothing is duplicated, so nothing can desynchronize.

## Install

```bash
npx skills add gulf1324/visualization-is-all-you-need
```

Or copy `SKILL.md`, `references/`, and `scripts/` into your project's skills
directory. The scripts are stdlib-only Python 3.8+ — no install step.

## Use

Ask your agent to "visualize this project" / "프로젝트 시각화해줘". It will
scan, propose a map, ask you for the parts it cannot infer, and validate before
showing you anything.

```bash
python scripts/scan_structure.py --suggest          # derive nodes/edges from the import graph
python scripts/validate_project_map.py PROJECT.md   # format + path rot
python scripts/scan_structure.py --compare PROJECT.md   # accuracy vs the code
```

## The two problems it actually solves

**Accuracy.** An agent's sense of "what depends on what" is a guess. Edges come
from the real import graph (Python, TS/JS, Go, Rust), and `--compare` reports
every cross-node import the map fails to draw, plus the percentage of source
files no node covers. A diagram nobody can trust is worse than none.

**Staleness.** Every architecture doc ever written rotted. Here, a deleted or
moved path fails the validator, a new dependency fails the audit, and both run
in `.githooks/pre-commit`. The map is maintained continuously, like `CLAUDE.md`
— not written once.

## What goes where

| | `CLAUDE.md` | `PROJECT.md` |
|---|---|---|
| Mood | imperative | declarative |
| Content | your instructions, commands, rules | what exists, how it connects, **why it is shaped this way** |
| Author | you | agent, from code + your decisions |

The `why` — `INVARIANT`, `CONSTRAINT`, `REJECTED`, `CONTRACT` per node — is the
part no amount of reading source recovers. `REJECTED` especially: an approach
that was tried and abandoned leaves no trace in the code at all.

## Honest limits

- Path existence is checked; whether a node's description still *matches* its
  code is not. No tool can check that.
- The scanner reads static imports in four languages. DI containers, dynamic
  imports, and runtime wiring are invisible to it.
- `stale-edge` is a report, not a verdict — spawns, HTTP calls, and queue
  writes are real dependencies with no import to prove them.
- Strictness is proportional to code: edges leaving a docs/config/shell node
  are `unverifiable`, not errors. A project with no parseable source gets a map
  that is useful but explicitly **not** machine-verified.

See `references/spec.md` for the format, `references/diagram-vocabulary.md` for
choosing a diagram kind, and `PROJECT.md` for this repo mapped with its own
format.
