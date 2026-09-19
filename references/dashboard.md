# Dashboard

```bash
python scripts/render_dashboard.py PROJECT.md          # -> PROJECT.html
python scripts/render_dashboard.py PROJECT.md --open   # and open it
python scripts/render_dashboard.py docs/PROJECT.md -o site/map.html
```

One self-contained HTML file. Diagram on the left, the selected node's full
ledger entry on the right, EN/KO toggle in the header.

## Read-only is structural, not a policy

The page is a build product: the map is serialized into it at generation time
and there is no `input`, `textarea`, `select` or `contenteditable` anywhere. No
amount of clicking can change what it says. The only path is

```
change the code  ->  update PROJECT.md  ->  re-run the renderer
```

The header states this, with the source file name and the generation time, so
a reader always knows what they are looking at and how old it is.

The renderer **refuses to build a map that fails validation**. A dashboard
makes a map look authoritative; rendering a broken one would dress up rot as a
product.

## Zoom is the detail mechanism

- Mouse wheel zooms toward the cursor, drag pans, `Reset view` restores.
- Clicking a node fills the panel with `role`, every `path:`, `OWNER`, and all
  `INVARIANT` / `CONSTRAINT` / `CONTRACT` / `REJECTED` lines, each colour-coded
  by kind. The selected node is outlined in the diagram.
- A node with a `map:` shows an **Open drill-down** button; the header grows a
  back link. Child maps are embedded in the same file, so drill-down works with
  no server and no second request.

## Languages

Two independent layers:

| Layer | Source | Always available |
|---|---|---|
| UI chrome (labels, legend, banner) | `STRINGS` in the renderer | yes |
| Map content (`role`, `why`, node labels, subgraph titles) | `PROJECT.<lang>.md` sibling | only if the file exists |

Create `PROJECT.ko.md` next to `PROJECT.md` with the **same node ids**. The
renderer merges it and the toggle then switches the diagram, the labels and the
ledger together — no screen ever shows two languages at once.

If the node ids diverge, the build fails:

```
error: ko: node ids differ in `PROJECT.ko.md`; missing ['release']
FAILED: a translation disagrees with the map it translates.
```

That is the point of the sibling-file design. Inline dual strings
(`role.en` / `role.ko`) were rejected: they double every ledger entry, and the
second language rots silently the moment someone edits only the first. A
sibling file reuses the format unchanged and makes the two node-id sets
comparable, so a half-updated translation cannot ship.

The cost is real and worth stating: a structural change must be made twice.
The renderer turns that cost into a build error instead of a silent lie.

## Mermaid comes from a CDN

`cdn.jsdelivr.net/npm/mermaid@11`. Vendoring ~3 MB into a repo whose premise is
"no install step" is the wrong trade, so the page needs network access once to
draw. Without it the diagram area explains the situation and the ledger still
renders.

## What it deliberately does not do

- **No editing, no live server, no file watcher.** Watching the map would
  invite editing in the browser; the code is the source and the map is the
  record.
- **No search or filter yet.** Below the 30-node limit the diagram is the
  index; above it, the answer is a `map:` drill-down, not a search box over a
  picture nobody can read.
- **No diff view.** Map history belongs to git.
