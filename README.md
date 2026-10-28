# LLM Evaluation Hub

A local catalog for LLM evaluation datasets. It snapshots a tabular source into conversation rows, stores segment values as columns, and groups datasets with a tag tree. A small HTTP API and a workbench browse that catalog. Register datasets from Python or import them through the workbench.

Documentation: [docs/index.md](docs/index.md).

## Setup

Linux or WSL on a local filesystem, with Python 3.12 or newer. From the repository root:

```bash
uv sync
```

The workbench also needs Node 22.22 or newer and `cd web && npm ci`. Contributor checks are in [Develop and test](docs/how-to/develop-and-test.md).

## Register a dataset

```python
from pathlib import Path

from llm_evaluation_hub.core.datasets import DatasetRepository, HfDatasetSource, ProcessedExample

repo = DatasetRepository(Path("data/catalog"))
repo.create_tag("Trendyol Cases")
repo.create_tag("classification", parent="Trendyol Cases")


def to_conversation(row: dict) -> ProcessedExample | None:
    text = row["text"]
    if not isinstance(text, str) or text == "":
        return None
    return ProcessedExample(
        conversation=[{"role": "user", "content": text}],
        expected_output=row["label"],
        segments={"language": str(row["language"])},
    )


repo.register(
    "trendyol-cases",
    HfDatasetSource("org/cases", "train", revision="main"),
    to_conversation,
    processor_id="cases.to_conversation",
    tags=["Trendyol Cases/classification"],
    segments=["language"],
)
```

`HF_TOKEN` is used when the source is constructed without a token. The token is not written into the catalog. The full steps, checks, and failures are in [docs/how-to/register-a-dataset.md](docs/how-to/register-a-dataset.md).

## Import from the workbench

Open `/datasets`, choose **Add dataset**, then follow the five-step form to sample a Hugging Face source, write and preview a processor, and submit a durable import job. See [Import a dataset in the workbench](docs/how-to/import-a-dataset.md).

## Run the API and workbench

```bash
LLM_EVAL_CATALOG=data/catalog uv run uvicorn llm_evaluation_hub.api.asgi:app --factory
```

```bash
cd web && npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/datasets`. When `LLM_EVAL_CATALOG` is unset, the API uses `data/catalog`. Details are in [docs/how-to/run-locally.md](docs/how-to/run-locally.md).

## Run with Docker

```bash
docker compose up --build
```

Open `http://127.0.0.1:8080/datasets`. The catalog volume starts empty and survives restarts. Set `LLM_EVAL_SEED=/opt/llm-eval/seed` to copy the demo catalog into an empty volume. The steps are in [docs/how-to/run-with-docker.md](docs/how-to/run-with-docker.md).

Before resetting a catalog volume, follow [Back up and recover](docs/how-to/backup-and-recover.md).
