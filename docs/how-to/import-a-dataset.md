---
type: Playbook
title: Import a dataset in the workbench
description: Use the five-step workbench form to sample a Hugging Face dataset, write a processor, preview rows, and submit an import.
tags: [datasets, workbench]
---

# Import a dataset in the workbench

Use this guide to create a catalog snapshot from a Hugging Face dataset in the browser. Start the API and workbench with [Run the API and workbench](run-locally.md), then open `http://127.0.0.1:5173/datasets` and choose **Add dataset**. The API must have Hub access for private datasets; configure `HF_TOKEN` on the API process as described in [Runtime configuration](../configuration/runtime.md).

The form has five steps. Dataset tags classify the whole snapshot. Segment keys classify each retained row. The processor computes each row's segment values. See [Workbench](../modules/workbench.md) for route behavior and [Core library](../modules/core.md) for the stored example contract.

## Enter dataset details

Enter a unique dataset name and optionally select existing hierarchical tags. Continue to source configuration. Tags must already exist in the catalog.

## Load and inspect a source sample

Choose Hugging Face and provide a Hub dataset repository ID, optional config, plain split name, revision, and row limit. The default revision is `main`; the row limit defaults to 10,000 and must be between 1 and 10,000. Choose **Load sample** to resolve the revision to a commit SHA and inspect up to ten raw rows and their observed columns.

The service uses the resolved SHA for later streaming. It accepts Hub repository identifiers and server-owned loader options. It does not accept local paths, arbitrary URLs, custom builders, or client-supplied loader arguments. The Hub token stays in backend configuration and is not part of the form or job specification.

## Declare segment keys

Select sampled source columns to use as segment keys, or add a custom key for a value calculated by Python. You can also leave the key list empty. Keys must follow the documented segment naming rules and cannot use reserved snapshot fields or `tools`. The processor must return exactly the declared keys, each with a string value.

## Write and preview the processor

Edit the generated `process(row)` function. It returns a dictionary containing `conversation`, `tools`, `expected_output`, `extras`, and `segments`, or returns `None` to skip a source row. The default tool list is empty. Tool definitions are per-row JSON data in the canonical function envelope:

```python
def process(row: dict) -> dict | None:
    return {
        "conversation": [{"role": "user", "content": row["text"]}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "lookup_order",
                    "description": "Look up an order by identifier",
                    "parameters": {
                        "type": "object",
                        "properties": {"order_id": {"type": "string"}},
                        "required": ["order_id"],
                    },
                },
            }
        ],
        "expected_output": row.get("label"),
        "segments": {"language": str(row["language"])},
    }
```

This example requires a declared `language` segment key and source columns named `text`, `label`, and `language`. Tool definitions describe available functions; the service does not execute them, validate the complete JSON Schema dialect, or resolve references. To map a source tools column, write the conversion in the processor. For JSON-encoded tool data, parse it in processor code with `json.loads`.

Choose **Run preview** to execute the processor on the cached sample. Inspect each kept, skipped, or failed row. A preview where every sampled row is skipped can pass; the complete import must retain at least one row. Preview success does not guarantee the full source will pass. A processor error on any imported row fails the job and publishes no partial snapshot.

The runtime is the constrained Monty Python subset. It does not provide host callbacks, external modules, filesystem or network access, and does not fall back to CPython. The processor source limit is 64 KiB; per-row input and output limits are 1 MiB; aggregate import input and output limits are 128 MiB; and row execution is limited to 250 ms. See [Core library](../modules/core.md) for the full policy limits.

## Review and submit

Review the name, tags, pinned source revision, row limit, segment keys, processor hash, and sample results. Choose **Import dataset** to create a durable job. The job page at `/dataset-imports/{id}` shows state, progress, and any safe diagnostic. The job list at `/dataset-imports` lets you rediscover submitted jobs after navigation or refresh.

You can cancel an active job. Failed, cancelled, or interrupted jobs do not publish a partial dataset. Retry opens the form with the previous settings filled in, but requires a fresh source sample and preview. Interrupted jobs are not resumed automatically. Successful jobs publish an immutable snapshot that you can inspect from the dataset catalog.

## If something fails

| Symptom | Action |
| --- | --- |
| Source sample cannot load | Check the Hub ID, config, split, revision, network access, and API-side `HF_TOKEN`; then load the sample again. |
| Processor preview fails | Read the row index, safe error, and code location. Correct the processor and preview again. |
| Preview is stale or expired | Load a fresh sample and run preview again. |
| Import job fails | Open its job page, correct the source or processor, and use retry to create a new job. |
| All source rows are skipped | Change the processor so at least one row is retained. Zero-row snapshots cannot be published. |
