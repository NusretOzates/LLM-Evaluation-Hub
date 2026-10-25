---
type: Reference
title: Purpose and scope
description: The catalog slice stores evaluation datasets locally and lets a workbench inspect them.
tags: [project]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Purpose and scope

LLM Evaluation Hub is a local catalog for datasets that will later be used to evaluate language models. This slice snapshots a tabular source into conversation rows, stores segment values as columns, and groups datasets with a tag tree.

The consumer is someone preparing or inspecting evaluation data on one machine. They register a dataset from Python, then browse tags, dataset metadata, and stored rows in the workbench or through HTTP.

## In scope

- Read a tabular source, including one Hugging Face dataset split.
- Turn each source row into one conversation record, or drop that row.
- Store the snapshot as Parquet and the catalog index in SQLite.
- Attach datasets to a tag tree and list a tag together with the datasets under it.
- Page through stored rows over HTTP and in the workbench.

## Out of scope

- Running a model, a judge, or a metric.
- Editing a stored row after registration. A snapshot is written once.
- Registering a dataset from the workbench or from HTTP. `DatasetRepository.register` is the only write path for snapshots.
- Authentication. The API allows every origin.

A processor returns one `ProcessedExample` or `None`. It cannot yet return several catalog rows from one source row. Split a trajectory into separate source rows, or into separate datasets, until that return type exists.
