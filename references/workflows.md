# Workflows

Three loops: **Init** once, **Update** on every structural change, **Read** at
the start of every session in a mapped repo.

## Init — first map for a repository

### 1. Determine the project's nature (before drawing)

Start with the import graph, because it is the only structural fact available
without judgment:

```bash
python scripts/scan_structure.py --suggest --depth 2
```

It prints how many source files and internal imports exist, a candidate node
grouping, and the edges it could prove. Read it as evidence, not as the answer:
it groups by directory, and a map groups by responsibility.

If it reports zero source files, the project is in a language it does not parse
(it handles Python, TS/JS, Go, Rust). Say so explicitly and derive structure by
reading — never let the user believe an unverified map was machine-checked.

Then read, in this order, stopping as soon as the structure is clear:

1. Build/manifest files — `package.json`, `pyproject.toml`, `Cargo.toml`,
   `go.mod`, `*.csproj`. Workspace members are your first candidate nodes.
2. Entry points — `main`, `index`, `cmd/`, `bin/`, route tables, `Dockerfile`
   `CMD`. These anchor the diagram's top.
3. Directory shape at depth 1–2 only. Do not descend further yet.
4. README/docs for stated intent — useful for `role:`, unreliable for structure.

Pick `kind:` using `diagram-vocabulary.md`. State your choice and its reason to
the user before writing the file.

### 2. Map responsibilities, not directories

A node is a thing that has a job. `src/utils/` is usually not a node; the thing
it serves is. Merge nodes you cannot describe in one line — an undescribable
node means the boundary is wrong.

Target 8–20 nodes for a first map. Below 8 the map says nothing; above 30 the
human stops reading. If the project is genuinely larger, the root map holds
domains and each domain gets a `map:` drill-down.

### 3. Draw edges you can prove

Every edge the scanner found is proven. Anything you add beyond those you must
have seen yourself — a spawn, an HTTP call, a queue write, a config reference.
A plausible-looking arrow you did not verify is exactly the failure mode that
makes maps untrustworthy.

The inverse matters too: an import the scanner found and you chose not to draw
is a decision you must be able to defend (usually "both files are inside one
node"). Declare `edges:` and any `edge-kinds:` you use.

### 4. Fill the ledger — mechanical first, then ask

`role:` and `path:` you can derive yourself. The UPPERCASE keys mostly you
cannot. Ask the user directly, naming nodes:

> For `store` and `engine`: (a) any invariant that must never break? (b) any
> external constraint that shaped this — budget, protocol, deadline? (c) did you
> try another approach here and reject it? The third one is the only thing in
> this file that cannot be recovered from the code later.

Record what the user says under `INVARIANT`/`CONSTRAINT`/`REJECTED`, and mark
anything you inferred yourself as inferred when you report back. Never invent a
`REJECTED` line — a fabricated decision history is worse than an empty one.

### 5. Validate before showing

```bash
python scripts/validate_project_map.py PROJECT.md      # format and path rot
python scripts/scan_structure.py --compare PROJECT.md  # accuracy vs the import graph
```

Exit 0 or it is not done. Warnings are the tool telling you the map will not
serve a human: over the node limit, unconnected nodes, or zero 'why' content.

### 6. Wiring — otherwise the map is dead weight

An unreferenced map never gets loaded. Add to the project's `CLAUDE.md`:

```markdown
## Project map
`PROJECT.md` is the structural source of truth: a Mermaid map plus a per-node
ledger of invariants, constraints, and rejected alternatives.

- Read `PROJECT.md` before exploring source or changing structure.
- A structural change (new/removed module, changed dependency, new external
  integration) is incomplete until `PROJECT.md` is updated in the same change.
- Validate with `python scripts/validate_project_map.py PROJECT.md`.
- Audit accuracy with `python scripts/scan_structure.py --compare PROJECT.md`.
- Never restate `PROJECT.md` content here. This file holds instructions; the map
  holds structure and rationale.
```

Enforcement, strongly recommended where the repo uses git hooks — run both
scripts in `pre-commit`. This is what turns "we should update the map" into
"the map cannot silently rot". Ship an escape hatch (an env var) or the whole
hook gets disabled the first time it is inconvenient.

## Update — on structural change

Run the audit first; it is cheaper and more reliable than recalling what
changed:

```bash
python scripts/scan_structure.py --compare PROJECT.md
```

| Report / change | Map edit |
|---|---|
| `missing-edge` | draw the edge, or merge the two nodes if the boundary was wrong |
| `uncovered` | extend a node's `path:`, or add the node the new code needs |
| New module/service | new node + edges + ledger entry |
| Deleted module | remove node, edges, and entry |
| Moved/renamed code | rebind `path:` — the validator fails until you do |
| Dependency added/removed | add/remove the edge |
| New external integration | new node with `path: -` |
| User states a decision or rejects an approach | `CONSTRAINT`/`REJECTED` line |

Touch only affected nodes. Re-run both scripts. Report what changed.

The last row is the one that gets skipped and the one that matters most. A
rationale is only available in the session it is spoken; a week later the code
remains and the reason is gone for good.

Two anti-patterns:

- **Silent restructure.** Shipping a structural change without a map update
  turns the map into a liar. Treat it as an incomplete change.
- **Map-first fiction.** Never add a node for code that does not exist yet. The
  map describes what is, not what is planned.

## Read — starting work in a mapped repo

1. Read `PROJECT.md` **before** any source exploration. That is the entire
   token argument: a few thousand tokens of map instead of dozens of file reads,
   and it tells you *why*, which no amount of reading source recovers.
2. Identify the nodes your task touches; open only the paths they name.
3. Honor the ledger. An `INVARIANT` is not a suggestion; a `CONSTRAINT` bounds
   your solution space; a `REJECTED` entry means do not propose that again
   without addressing the recorded reason.
4. If the map contradicts the code, **the map is stale** — say so explicitly,
   fix it in the same session, and tell the user what was wrong. A contradiction
   found and left in place is the beginning of rot.
