---
type: Reference
title: Workbench
description: React Router pages that browse tags, datasets, and one stored row at a time.
tags: [workbench]
generated: { by: human:nusret, at: 2026-10-25T22:04:00+03:00 }
status: stable
---

# Workbench

The site in `web/` is a React Router application with server rendering off (`web/react-router.config.ts`). `/` redirects to `/datasets`. The browser calls `/api/...`. `web/app/catalog.ts:request` parses JSON and maps a network failure to the message `The catalog API is not reachable.` Visual tokens and layout rules are in [Workbench design](workbench-design.md).

| Route | Loader | What it shows |
| --- | --- | --- |
| `/datasets` | `GET /tags` is loaded by the root route. This route loads `GET /datasets` and optional `?tag=`. | Dataset table. The sidebar tag tree filters that list. |
| `/datasets/:name` | Dataset, one example page, and the tag forest | One selected row, with the page of rows beside it |

`POST /tags` runs from the sidebar form and posts to the `/datasets` route action. Attach and detach post to the dataset route action and call `POST` or `DELETE /datasets/{name}/tags`.

## Dataset list

Each table row links to `/datasets/{name}`. Columns are name and processor id, source coordinates, rows kept, retention, segment names, tag leaf names, and the created date. Retention is `rows_kept / rows_loaded`, shown as a percent. A selected tag is a removable chip. The chip clears `?tag`.

The sidebar lists every tag. The count on a tag is the number of datasets whose tag equals that path or starts with `path/`. That is the same descendant rule as `GET /datasets?tag=`. Collapsing the sidebar keeps the tag tree off the list page until you expand it. The dataset page starts with the sidebar collapsed. `[` toggles it. The list page and the dataset page remember that choice separately in `localStorage` keys `sidebar-collapsed` and `sidebar-collapsed-detail`.

## Row inspector

The loader asks for 50 examples. `?offset` selects the page. `?row` selects a 1-based row. When `row` is omitted, the first row of the page is selected. `j` and `k` move one row and change `offset` when the selection crosses a page boundary. Previous and next page links change `offset` by 50.

The filter box searches the current page. A query that is only digits is not a text filter. Submitting that value jumps to that row number. `/` focuses the box. When the first segment key on the page has 2 to 8 distinct values, those values appear as buttons that filter the page.

The reader shows one conversation. An empty system message is omitted. A non-empty system message is collapsed to one line. A tool call is shown as `name(arguments)`. String `expected_output` is prose. Any other JSON value is pretty-printed. `extras` is a field list. **JSON** shows the stored example. **Copy** writes that JSON to the clipboard.

`\` toggles the row list (`localStorage` key `dataset-index`). `]` toggles the details aside (`dataset-aside`). The aside edits tag links and lists source fields. Null provenance fields are omitted.

These shortcuts do nothing while focus is in a text field, a select, or an editable element.

The workbench has no test suite. Check it with `cd web && npm run typecheck`.
