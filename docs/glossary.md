---
type: Reference
title: Glossary
description: Names shared by the catalog, the API, and the workbench.
tags: [glossary]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Glossary

| Term | Meaning |
| --- | --- |
| Catalog | The directory that contains `catalog.sqlite` and `datasets/<id>/rows.parquet`. |
| Dataset | One named snapshot plus its metadata and direct tag links. |
| Snapshot | The Parquet file written by one successful `register` call. It is not updated in place. |
| Source row | One row of the frame returned by `DatasetSource.read`, before the processor drops it. |
| Stored row | One `ProcessedExample` in the snapshot. The examples API numbers these from 1 in file order. |
| Processor | The function passed to `register`. It returns one `ProcessedExample` or `None`. |
| `processor_id` | A non-empty string recorded on the dataset so a later reader can see which function produced the snapshot. |
| Conversation | The `conversation` message list on a stored row. |
| Expected output | The `expected_output` JSON value. Null means the processor set no gold value. |
| Extras | A JSON object of extra judge context. It is not a segment and not the gold output. |
| Segment | A string column declared for every stored row, such as `language`. It describes the row, not the dataset. |
| Tag | A node in the forest. Its path is the names from the root joined by `/`. |
| Tag link | A row in `dataset_tags` between one dataset and one existing tag. |
| Retention | In the workbench, `rows_kept / rows_loaded` for that dataset. |
