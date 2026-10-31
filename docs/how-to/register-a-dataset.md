---
type: Playbook
title: Register a dataset
description: Create tags, map source rows to conversations, and store a snapshot the API can read.
tags: [datasets]
generated: { by: human:nusret, at: 2026-10-25T19:00:00+03:00 }
status: stable
---

# Register a dataset

Run this in the same catalog directory the API serves. See [Run the API and workbench](run-locally.md). The processor contract is in [Core library](../modules/core.md).

## Steps

1. Point `DatasetRepository` at the catalog directory:

```python
from pathlib import Path

from llm_evaluation_hub.core.datasets import DatasetRepository, HfDatasetSource, ProcessedExample

repo = DatasetRepository(Path("data/catalog"))
```

2. Create tag nodes before linking them. `create_tag` does not attach a dataset:

```python
repo.create_tag("Trendyol Cases")
repo.create_tag("classification", parent="Trendyol Cases")
repo.create_tag("Language")
repo.create_tag("Turkish", parent="Language")
```

3. Map each source row to one example. Return `None` to drop a row:

```python
def to_conversation(row: dict) -> ProcessedExample | None:
    text = row["text"]
    if not isinstance(text, str) or text == "":
        return None
    return ProcessedExample(
        conversation=[{"role": "user", "content": text}],
        expected_output=row["label"],
        segments={"language": str(row["language"]), "difficulty": str(row["difficulty"])},
    )
```

4. Register the snapshot. `segments` must be exactly the keys the processor sets:

```python
repo.register(
    "trendyol-cases-multilingual",
    HfDatasetSource("org/cases", "train", revision="main"),
    to_conversation,
    processor_id="cases.to_conversation",
    tags=["Trendyol Cases/classification", "Language/Turkish"],
    segments=["language", "difficulty"],
)
```

5. Confirm the write:

```python
record = repo.get("trendyol-cases-multilingual")
assert record.rows_kept > 0
page = repo.examples("trendyol-cases-multilingual", offset=0, limit=1)
assert page[0].conversation[0].role == "system"
```

The conversation preserves the messages returned by the processor. `GET /datasets/trendyol-cases-multilingual` on the API returns the same metadata, without `parquet_path`.

## Failures

| Symptom | Cause |
| --- | --- |
| `dataset already exists: trendyol-cases-multilingual` | The name is taken. Pick another name. Snapshots are not replaced. |
| `unknown tag: ...` | Call `create_tag` for that path before `register`. |
| `processor kept zero rows` | Every row returned `None` or the source frame was empty. |
| `row N failed: ...` | The processor raised, or the segment keys did not match `segments`. Nothing was stored. |
| Hub auth error from `HfDatasetSource` | Set `HF_TOKEN` or pass `token=` . The token is not written into `data/catalog`. |

`limit=100` on `register` asks the source for a prefix before processing. For `HfDatasetSource`, the split must be a plain name such as `train`.
