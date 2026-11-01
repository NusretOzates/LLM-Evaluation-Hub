---
type: Reference
title: Evaluation runs
description: Evaluate saved inference responses and inspect score coverage.
tags: [evaluation]
status: draft
---

# Evaluation runs

An evaluation uses one terminal inference run and a nonempty set of its frozen datasets. Every selected retained row contributes to the denominator. Missing or unsuccessful predictions and missing required references are ineligible; method and scoring failures do not produce scores. A metric mean uses only valid scored rows, while coverage is scored rows divided by selected rows. A mean without scored rows is null. Summaries group by dataset, frozen segment or frozen tag path; tag ancestors include descendants and overlapping groups are not totals.

Exact match compares JSON values without normalizing text. Boolean and number are distinct, numbers compare numerically, object key order is ignored, and array order matters. Use optional `preprocess(response)` to select or normalize a candidate. The function sees only `content`, `parsed` and `tool_calls`, not references. A null content needs preprocessing.

The LLM judge sends a single user message and an object-root structured output schema. Prompt placeholders are literal `{{path}}` substitutions, not expressions. The candidate is data, not an instruction. The scoring function `score(result)` receives only the validated judgment and must return a nonempty dictionary of named finite numbers. Each score must match its declared key and optional bounds. Boolean judgments require `int()` conversion. Editor code runs in capability-free Monty.

Runs freeze settings, dataset names, tags, segments, source result presence and status. Source snapshots and inference results remain referenced while an evaluation is queued, running, canceling or interrupted: purge, source deletion and resume are guarded. After completion or cancellation, sources can be deleted; retained score and judge evidence remains, but input inspection reports unavailable. Evaluation deletion removes only its own manifest and outcomes. Startup interrupts unfinished work; resume is explicit and skips committed outcomes. In-flight requests may be resent after a crash.

A developer adds a trusted method module and registers a `MethodDefinition` in `evaluation/registry.py`: provide configuration validation, result schema, scoring default, resource capability and a run-scoped async session. The session returns a JSON object in `MethodOutcome`; shared execution validates and scores it. Code execution and math equivalence are not built in. A judge integration check does not establish judge accuracy.

Catalog schema v6 is current. There is no automatic migration or reset. A fresh catalog reset permanently removes catalog datasets, history and connection profiles; back it up first. The model container and model cache are separate from the catalog volume.
