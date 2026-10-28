---
type: Reference
title: Workbench
description: React Router pages that browse tags, datasets, and one stored row at a time.
tags: [workbench]
generated: { by: process:codex-refactor, at: 2026-10-26T13:56:10+03:00 }
status: stable
---

# Workbench

The site in `web/` is a React Router application with server rendering off (`web/react-router.config.ts`). `/` redirects to `/datasets`. The browser calls `/api/...`. `web/app/catalog.ts:request` parses JSON and maps a network failure to the message `The catalog API is not reachable.` Visual tokens and layout rules are in [Workbench design](workbench-design.md).

| Route | Loader | What it shows |
| --- | --- | --- |
| `/datasets` | `GET /tags` is loaded by the root route. The root loads all datasets once; this route applies optional `?tag=` to that shared data. | Dataset table. The sidebar tag tree filters that list. |
| `/datasets/:name` | UUID metadata and one example page; tags come from the root | One selected row, with the page of rows beside it |
| `/dataset-imports/new` | Source, sample, preview, and catalog metadata | Five-step dataset import form |
| `/dataset-imports` | Persisted import jobs | Job list for rediscovery |
| `/dataset-imports/:id` | One persisted job | Progress, diagnostics, result, and retry entry point |

`POST /tags` runs from the sidebar form and posts to the `/datasets` route action. Attach and detach post to the dataset route action and call `POST` or `DELETE /dataset-ids/{id}/tags`.

## Dataset list

Each table row links to `/datasets/{id}` using the immutable UUID. Existing single-segment name bookmarks still resolve through the compatibility lookup. Columns are name and processor id, source coordinates, rows kept, retention, segment names, tag leaf names, and the created date. Retention is `rows_kept / rows_loaded`, shown as a percent. A selected tag is a removable chip. The chip clears `?tag`.

The sidebar lists every tag. The count on a tag is the number of datasets whose tag equals that path or starts with `path/`. That is the same descendant rule as `GET /datasets?tag=`. Collapsing the sidebar keeps the tag tree off the list page until you expand it. The dataset page starts with the sidebar collapsed. `[` toggles it. The list page and the dataset page remember that choice separately in `localStorage` keys `sidebar-collapsed` and `sidebar-collapsed-detail`.

## Row inspector

The loader asks for 50 examples. `?offset` selects the page. `?row` selects a 1-based row. When `row` is omitted, the first row of the page is selected. `j` and `k` move one row and change `offset` when the selection crosses a page boundary. Previous and next page links change `offset` by 50.

The filter box searches the current page. A query that is only digits is not a text filter. Submitting that value jumps to that row number. `/` focuses the box. When the first segment key on the page has 2 to 8 distinct values, those values appear as buttons that filter the page. Page and dataset changes reset text/facet filters. URL indices must be safe integers.

The reader shows one conversation and the selected row’s available tool definitions. Tool definitions are expandable JSON descriptions; they are not executed. **JSON** and **Copy** include the complete definitions.

## Dataset imports

The five-step form at `/dataset-imports/new` collects dataset name and tags, Hugging Face source coordinates, segment keys, processor code, and review details. It loads a source sample before preview. A preview is required before submission. The sample and preview can expire and must then be refreshed. See [Import a dataset in the workbench](../how-to/import-a-dataset.md) for the complete user procedure.

The job list and detail pages read durable job state. Cancellation and terminal results come from the API. Retry pre-fills the form from the prior specification and requires a new sample and preview.

An empty system message is omitted. A non-empty system message is collapsed to one line. A tool call is shown as `name(arguments)`. String `expected_output` is prose. Any other JSON value is pretty-printed. `extras` is a field list. **JSON** shows the stored example. **Copy** writes that JSON to the clipboard. Failure shows feedback and leaves the JSON view available. Blocked browser storage falls back to in-memory panel preferences.

`\` toggles the row list (`localStorage` key `dataset-index`). `]` toggles the details aside (`dataset-aside`). The aside edits tag links and lists source fields. Null provenance fields are omitted.

These shortcuts do nothing while focus is in a text field, a select, or an editable element.

Unit and real-browser regression checks are described in [Develop and test](../how-to/develop-and-test.md). Runtime parsing rejects malformed required fields rather than replacing them with empty data.
