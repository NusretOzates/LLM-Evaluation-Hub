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

| Route | What it shows |
| --- | --- |
| `/datasets` | Active datasets, name search, and match-all tag filters |
| `/datasets/:name` | One example, its page of examples, and dataset metadata |
| `/tags` | Searchable tag tree and selected-tag management |
| `/dataset-imports/new` | Four-step dataset import form |
| `/dataset-imports` and `/dataset-imports/:id` | Import history and job details |
| `/trash` | Restore or permanently delete trashed snapshots |

## Dataset list and tags

The root loader retrieves the tag forest and active datasets. Dataset search uses `q`; each `tag` parameter adds a match-all filter. A tag matches direct assignments and descendants separated by `/`. Unknown paths remain visible as unavailable filters and match no datasets. Name search replaces the current history entry; selecting or removing tags and clearing filters creates a history entry. Unrelated query parameters are preserved.

The `/tags` tree uses `selected` for the detail path and `q` for tree search. Details show the number of directly tagged active datasets and distinct datasets in the branch. Create a top-level tag or a sub-tag from this page. Deletion can remove a subtree or remove a grouping and promote its children; confirmations show the affected scope. Dataset records remain intact. Attach and detach dataset tags from the inspector metadata pane.

Dataset links use immutable IDs; existing single-segment name bookmarks still resolve through the compatibility lookup. At narrow widths cards expose secondary metadata under Details. Dataset actions move a snapshot to Trash after confirmation. Names remain reserved in Trash until restoration or permanent deletion. Import history remains available after a dataset is trashed or purged.

The sidebar collapse preference is stored separately for catalog and inspector views under `sidebar-collapsed` and `sidebar-collapsed-detail`. `[` toggles the current view. Appearance is System, Light, or Dark and is stored as `evaluation-hub.theme` when browser storage is available.

## Row inspector

The loader asks for 50 examples. `?offset` selects the page. `?row` selects a 1-based row. When `row` is omitted, the first row of the page is selected. `j` and `k` move one row and change `offset` when the selection crosses a page boundary. Previous and next page links change `offset` by 50.

The filter box searches the current page. A query that is only digits is not a text filter. Submitting that value jumps to that row number. `/` focuses the box. Choose a Segment, then choose its Value to filter the current page. The value selector is available for any number of distinct values, including one; empty strings appear as `(Empty value)`, separately from `All values`. Changing the segment resets its value filter. Page and dataset changes reset text/facet filters. URL indices must be safe integers.

The reader shows one conversation and the selected row’s available tool definitions. Tool definitions are expandable JSON descriptions; they are not executed. **JSON** and **Copy** include the complete definitions.

## Dataset imports

The four-step form at `/dataset-imports/new` collects dataset name and tags, Hugging Face source coordinates, processor code, and review details. The tag selector shows collapsible branches and keeps ancestors visible during search. Selecting an ancestor or descendant replaces the redundant selection; siblings can be selected together. Segment columns can be selected after sampling, and custom segments are defined in Python. It loads a source sample before preview. A preview is required before submission. The sample and preview can expire and must then be refreshed. See [Import a dataset in the workbench](../how-to/import-a-dataset.md) for the complete user procedure.

The job list and detail pages read durable job state. Cancellation and terminal results come from the API. Retry pre-fills the form from the prior specification and requires a new sample and preview.

Supplied system messages are shown in a collapsed section. A tool call is shown as `name(arguments)`. String `expected_output` is prose. Any other JSON value is pretty-printed. `extras` is a field list. **JSON** shows the stored example. **Copy** writes that JSON to the clipboard. Failure shows feedback and leaves the JSON view available. Blocked browser storage falls back to in-memory panel preferences.

`\` toggles the row list (`localStorage` key `dataset-index`). `]` toggles the details aside (`dataset-aside`). The aside edits tag links and lists source fields. Null provenance fields are omitted.

These shortcuts do nothing while focus is in a text field, a select, or an editable element.

Unit and real-browser regression checks are described in [Develop and test](../how-to/develop-and-test.md). Runtime parsing rejects malformed required fields rather than replacing them with empty data.
