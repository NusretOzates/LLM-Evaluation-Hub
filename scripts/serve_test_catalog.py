"""Serve an isolated synthetic catalog for browser regression tests."""

from pathlib import Path
from tempfile import TemporaryDirectory

import polars as pl
import uvicorn
from test_source_adapter import TrustedSyntheticAdapter

from llm_evaluation_hub.api import create_app
from llm_evaluation_hub.core.datasets import DatasetRepository, ProcessedExample
from llm_evaluation_hub.core.datasets.sources.protocol import SourceDescriptor


class FixtureSource:
    """Generate page-boundary fixtures without external data access."""

    def read(self, *, limit: int | None = None) -> pl.DataFrame:
        """Return enough rows to cross a workbench page boundary."""
        frame = pl.DataFrame({"index": list(range(61))})
        return frame if limit is None else frame.head(limit)

    def describe(self) -> SourceDescriptor:
        """Identify this source as synthetic test data."""
        return SourceDescriptor(source_type="browser-fixture")


def processor(row: dict[str, object]) -> ProcessedExample:
    """Include facets that change from multiple values to one across pages."""
    index = int(str(row["index"]))
    return ProcessedExample(
        conversation=[{"role": "user", "content": f"Synthetic row {index + 1}"}],
        expected_output={"index": index},
        extras={"rubric": "Synthetic fixture only"},
        segments={"group": "c" if index >= 50 else "a" if index % 2 == 0 else "b"},
    )


def main() -> None:
    """Run on the same fixed loopback API port used by the Vite test proxy."""
    with TemporaryDirectory(prefix="llm-hub-browser-") as temporary:
        root = Path(temporary)
        repo = DatasetRepository(root)
        repo.create_tag("__proto__")
        repo.create_tag("Browser")
        repo.register(
            "team/cases %?#",
            FixtureSource(),
            processor,
            processor_id="tests.browser",
            segments=["group"],
        )
        uvicorn.run(
            create_app(root, source_adapter=TrustedSyntheticAdapter()),
            host="127.0.0.1",
            port=8000,
        )


if __name__ == "__main__":
    main()
