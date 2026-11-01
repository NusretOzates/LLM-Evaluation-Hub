"""Contracts shared by evaluation methods and execution."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm_evaluation_hub.core.datasets.records import ProcessedExample


class Metric(BaseModel):
    """A score name and its optional display bounds."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(min_length=1)
    minimum: float | None = None
    maximum: float | None = None
    direction: Literal["higher", "lower"] = "higher"

    @model_validator(mode="after")
    def ordered_bounds(self) -> "Metric":
        """Reject reversed ranges."""
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class Definition(BaseModel):
    """Reusable evaluation settings; runs freeze a copy."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    method_id: str = Field(min_length=1)
    method_config: dict[str, Any] = Field(default_factory=dict)
    preprocess_source: str | None = None
    scoring_source: str
    metrics: list[Metric] = Field(min_length=1)
    concurrency: int = Field(default=1, ge=1, le=100)

    @model_validator(mode="after")
    def unique_metrics(self) -> "Definition":
        """Ensure every metric has one declaration."""
        if len({m.name for m in self.metrics}) != len(self.metrics):
            raise ValueError("metric names must be unique")
        return self


@dataclass(frozen=True)
class MethodContext:
    """Input available to a method, distinct from scoring input."""

    example: ProcessedExample
    response: dict[str, Any]
    candidate: Any
    dataset_id: str
    ordinal: int
    source_index: int


@dataclass(frozen=True)
class MethodOutcome:
    """A validated judgment and optional method-specific evidence."""

    result: dict[str, Any]
    evidence: Any = None
    elapsed_ms: float | None = None
    attempts: int = 0
    usage: dict[str, Any] = field(default_factory=dict)


class SourceIneligible(Exception):
    """A source row lacks required data for a method."""


class MethodFailure(Exception):
    """A per-row failure with retained evidence from the method."""

    def __init__(
        self,
        message: str,
        *,
        evidence: object = None,
        elapsed_ms: float | None = None,
        attempts: int = 0,
        usage: object = None,
    ) -> None:
        """Initialize the owned evaluation state."""
        super().__init__(message)
        self.evidence = evidence
        self.elapsed_ms = elapsed_ms
        self.attempts = attempts
        self.usage = usage


class EvaluationServices(Protocol):
    """Catalog-bound services available during method setup."""

    root: Path


class EvaluationSession(Protocol):
    """Run-scoped method resources."""

    async def evaluate(self, context: MethodContext) -> MethodOutcome:
        """Evaluate one candidate."""
        ...
