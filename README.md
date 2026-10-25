# LLM-Evaluation-Hub

A single hub for evaluation of LLMs. This slice is a local dataset catalog: it snapshots a Hugging Face dataset into conversation records, stores row segments as columns, and organizes datasets with a tag tree.

## Register a dataset

```python
from pathlib import Path

from llm_evaluation_hub.core.datasets import DatasetRepository, HfDatasetSource, ProcessedExample

repo = DatasetRepository(Path("data/catalog"))
repo.create_tag("Trendyol Cases")
repo.create_tag("classification", parent="Trendyol Cases")
repo.create_tag("Language")
repo.create_tag("Turkish", parent="Language")


def to_conversation(row: dict) -> ProcessedExample:
    return ProcessedExample(
        conversation=[{"role": "user", "content": row["text"]}],
        expected_output=row["label"],
        segments={"language": row["language"], "difficulty": row["difficulty"]},
    )


repo.register(
    "trendyol-cases-multilingual",
    HfDatasetSource("org/cases", "train", revision="main"),
    to_conversation,
    processor_id="cases.to_conversation",
    tags=["Trendyol Cases/classification", "Language/Turkish"],
    segments=["language", "difficulty"],
)

repo.rows("trendyol-cases-multilingual")
repo.list_datasets(tag="Trendyol Cases")
```

`create_tag` adds a node to the tree and does not attach it to a dataset. Pass tag paths to `register`, or call `add_tags` and `remove_tags` later. Listing a parent tag includes datasets linked to tags under it.

A segment is a string column on each row, such as `language` or `difficulty`. A dataset tag still describes the dataset as a whole. `HF_TOKEN` is read from the environment when the source is constructed without a token, and the token is not written into the catalog.

A single-input row is stored as a conversation. When the processor does not start with a system message, an empty system message is inserted.

## Run the API

```bash
LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
```

`LLM_EVAL_CATALOG` selects the catalog directory. When it is unset, the app uses `data/catalog`.

`GET /tags` and `POST /tags` use the same nested dict. A post creates any missing nodes:

```json
{
  "Trendyol Cases": {
    "children": {
      "Summarization": {
        "children": {
          "Review Summarization": {}
        }
      }
    }
  }
}
```

The response fills `path` on each node. `GET /datasets` returns dataset metadata, and `GET /datasets/{name}/examples` returns a page of stored rows.
