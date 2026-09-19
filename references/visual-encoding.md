# Visual encoding

The diagram is the human-facing half of the artifact. Its job is to answer a
reader's first questions **without a lookup**:

1. What are the parts, and what is each one for?
2. Where do I start reading?
3. What can I open further?
4. What has no code behind it?
5. What does an arrow mean here?

A diagram of bare ids answers only "what connects to what" and defers
everything else to the ledger. With 11 nodes that is 11 round trips before the
reader understands anything. The encoding below removes them.

## Text first, colour second — and why

Mermaid renders in two very different places: GitHub (SVG, full styling) and a
terminal (ASCII, where `classDef` colour is dropped and node shapes are often
normalized). A signal carried only by colour is **invisible to whoever reads in
a terminal** — which includes every agent-driven session.

So every load-bearing signal is ASCII text inside the label. Colour and shape
are added on top as enhancement for the web view, never as the only carrier of
a fact. This is the same rule that keeps the 'why' out of `%%` comments: if one
of the two audiences cannot see it, it does not count as encoded.

## The encoding

### Label: two lines

```
id["display name<br/>short role"]
```

Line 1 is the display name (a filename, a module, a service). Line 2 is a
shortened `role:`, at most 52 characters.

The role is duplicated between diagram and ledger on purpose: it is what makes
the diagram self-sufficient. The duplication is safe because the validator
requires line 2 to be how `role:` **starts** — a label that says something the
ledger does not is an error, not a style nit.

Labels must be quoted (`["..."]`), otherwise the label text cannot be read back
and checked.

### Sigils: appended to the display name

| Sigil | Meaning | Derived from | Enforcement |
|---|---|---|---|
| `*` | nothing depends on this — start reading here | in-degree 0 | error if something depends on it; warn if an in-degree-0 node lacks it |
| `+` | has a drill-down map | `map:` present | error if the two disagree |
| `~` | no code behind it (external system, convention, policy) | every `path:` is `-` | error if the two disagree |

```
plugin([".claude-plugin/ *<br/>install manifests"])
billing[["billing +<br/>invoicing, dunning, tax"]]
stripe["Stripe ~<br/>card charges and webhooks"]
```

Because each sigil is derived from a ledger fact, sigil drift is mechanically
detectable. None of them are decoration.

### Shape and colour: enhancement only

| Node | Shape | Class |
|---|---|---|
| entry point | `(["..."])` stadium | `entry` |
| drill-down | `[["..."]]` subroutine | — |
| no code | `["..."]` with dashed border | `external` |
| ordinary | `["..."]` | — |

```
classDef entry fill:#1f6feb,stroke:#58a6ff,color:#ffffff
classDef external fill:none,stroke:#8b949e,stroke-dasharray:4 3,color:#8b949e
class plugin,claude_md entry
```

Shapes and classes are **not** validated: a terminal renderer may ignore them,
so enforcing them would punish a map that reads fine where it matters. The
sigils already carry the same facts.

### Legend: markdown under the diagram

```markdown
Arrows mean **depends-on** unless labeled.
`*` nothing depends on it — start reading here · `+` has a drill-down map ·
`~` no code behind it.
```

`edges:` in `## Meta` is machine-readable but sits far from the picture, in
key/value form. The legend restates it where the eye already is. Two lines, and
it makes the arrows self-explaining.

## Layout stability

Mermaid auto-layout is not stable across edits: adding one node can reshuffle
the whole picture and destroy the reader's spatial memory of it. Rules that
keep it usable:

- Fix the direction (`flowchart TD`) and never flip it to "make it fit".
- Group with `subgraph` by domain. Grouping anchors position far better than
  edge order does. A `subgraph` id is a container, not a node — it needs no
  ledger entry, and `container --> node` is legal.
- Prefer additive edits. Rewriting the whole block for a cosmetic reason costs
  the reader their memory of the layout for nothing.
- Above 30 nodes, split into `map:` drill-downs instead of shrinking labels.
- **Collapse a fan of same-kind leaves.** More than about four leaf nodes
  hanging off one parent are laid out in a single row, and the diagram grows
  sideways until the labels collide. Measured on a real map: five sibling
  library nodes produced a 7704 px-wide image with overlapping text; folding
  them into one `+` node with a drill-down brought it to 3650 px and removed
  the collisions. `subgraph ... direction TB` does **not** fix this — Mermaid
  ignores a subgraph's direction when the subgraph has edges to outside nodes.
- **Keep the display name short in a stadium node.** `(["..."])` clips its
  label earlier than a rectangle does; a long first line gets cut off with no
  warning from any tool.

## Generated for you

`scan_structure.py --suggest` emits the encoding already applied — two-line
labels, `*` on every in-degree-0 node, stadium shapes, `classDef`, and the
legend. Its output validates as-is; you replace the `TODO describe this`
placeholders in **both** the label and the ledger (they must agree) and add the
`why` keys from the user.

A standard that costs manual effort on every node does not get followed, so the
generator, not the user, pays for it.
