"""Strict JSON exact-match method."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from pydantic import BaseModel, ConfigDict

from llm_evaluation_hub.core.datasets.records import ProcessedExample
from llm_evaluation_hub.evaluation.contracts import (
    EvaluationServices,
    MethodContext,
    MethodOutcome,
    SourceIneligible,
)


class ExactMatchConfig(BaseModel):
    """Exact matching has no configuration."""

    model_config = ConfigDict(extra="forbid")


def equal_json(left: object, right: object) -> bool:
    """Compare JSON types strictly, treating finite integer and float values numerically."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            equal_json(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(
            equal_json(left[key], right[key]) for key in left
        )
    return left == right


def check_source(example: ProcessedExample) -> None:
    """Require a reference independently of the candidate representation."""
    if example.expected_output is None:
        raise SourceIneligible("expected output is missing")


class ExactMatchSession:
    """Perform local comparisons without external resources."""

    async def evaluate(self, context: MethodContext) -> MethodOutcome:
        """Compare the candidate with the reference."""
        if context.example.expected_output is None:
            raise SourceIneligible("expected output is missing")
        return MethodOutcome(
            result={"matches": equal_json(context.candidate, context.example.expected_output)}
        )


@asynccontextmanager
async def open_session(
    config: dict[str, Any], services: EvaluationServices
) -> AsyncGenerator[ExactMatchSession]:
    """Validate configuration and open a local method session."""
    del services
    ExactMatchConfig.model_validate(config)
    yield ExactMatchSession()
