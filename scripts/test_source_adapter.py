"""Importable, picklable Hugging Face fixtures for real browser journeys."""

from collections.abc import Iterator
from time import sleep

from llm_evaluation_hub.imports.contracts import SourceSpec
from llm_evaluation_hub.imports.runtime import ProcessorError


def _lookup_order() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up an order by identifier.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    }


def _search_catalog() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": "Search the product catalog.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    }


def _row(index: int) -> dict[str, object]:
    tools = [_lookup_order()] if index == 0 else [_search_catalog()] if index == 1 else []
    return {
        "text": ["Siparişimin durumu nedir?", "Find this product.", "Merhaba!"][index % 3],
        "label": f"Expected answer {index + 1}",
        "language": "tr" if index in {0, 2} else "en",
        "difficulty": "basic" if index == 0 else "advanced" if index == 1 else "basic",
        "tools": tools,
    }


class TrustedSyntheticAdapter:
    """Serve fixed JSON fixture rows inside real spawned API worker processes."""

    def resolve(self, source: SourceSpec) -> str:
        """Pin known synthetic Hub-shaped identifiers to stable local revisions."""
        if source.repo_id not in {
            "fixtures/cases",
            "fixtures/later-error",
            "fixtures/slow",
            "fixtures/sample-delay",
        }:
            raise ProcessorError("source", "Use one of the local browser test repositories.")
        return f"synthetic-{source.repo_id.rsplit('/', 1)[-1]}-sha"

    def rows(
        self, source: SourceSpec, resolved_sha: str, limit: int
    ) -> Iterator[dict[str, object]]:
        """Yield distinct sample/import prefixes, including bounded failure fixtures."""
        del resolved_sha
        if source.repo_id == "fixtures/sample-delay":
            if limit <= 10:
                sleep(1)
            yield from [_row(index) for index in range(min(3, limit))]
            return

        if source.repo_id == "fixtures/later-error":
            rows = [_row(0), _row(1), _row(2)]
            if limit > 10:
                rows.append({**_row(3), "tools": [{"type": "not-a-function"}]})
            yield from rows[:limit]
            return

        if source.repo_id == "fixtures/slow":
            count = 3 if limit <= 10 else 30
            for index in range(min(count, limit)):
                if limit > 10 and index >= 3:
                    sleep(0.1)
                yield _row(index)
            return

        yield from [_row(index) for index in range(min(3, limit))]
