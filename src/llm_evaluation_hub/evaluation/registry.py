"""Explicit extensible registry of evaluation methods."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from llm_evaluation_hub.evaluation.contracts import EvaluationServices
from llm_evaluation_hub.evaluation.methods.exact_match import (
    ExactMatchConfig,
    check_source,
    open_session,
)
from llm_evaluation_hub.evaluation.methods.llm_judge import JudgeConfig
from llm_evaluation_hub.evaluation.methods.llm_judge import open_session as open_judge
from llm_evaluation_hub.evaluation.methods.llm_judge import preflight as preflight_judge
from llm_evaluation_hub.evaluation.methods.llm_judge import preview as preview_judge
from llm_evaluation_hub.evaluation.methods.llm_judge import resolve as resolve_judge
from llm_evaluation_hub.evaluation.methods.llm_judge import validate_prompt as validate_judge_fields


@dataclass(frozen=True)
class MethodDefinition:
    """Method metadata and lifecycle hooks."""

    id: str
    version: int
    label: str
    config_model: type[BaseModel]
    result_schema: Callable[[dict[str, Any]], dict[str, Any]]
    open: Callable[..., Any]
    default_scoring: str
    resource: str = "local"
    resolver: Callable[..., dict[str, Any]] | None = None
    preflight: Callable[..., None] | None = None
    validate_fields: Callable[..., None] | None = None
    preview: Callable[..., dict[str, Any]] | None = None
    check_source: Callable[..., None] | None = None

    def resolve_config(
        self, config: dict[str, Any], services: EvaluationServices
    ) -> dict[str, Any]:
        """Validate and freeze configuration."""
        if self.resolver is not None:
            return self.resolver(config, services)
        return self.config_model.model_validate(config).model_dump(mode="json")


METHODS: dict[str, MethodDefinition] = {}


def register(method: MethodDefinition) -> None:
    """Register a method once under its stable identifier."""
    if method.id in METHODS:
        raise ValueError(f"duplicate evaluation method: {method.id}")
    METHODS[method.id] = method


register(
    MethodDefinition(
        id="exact_match",
        version=1,
        label="Exact match",
        config_model=ExactMatchConfig,
        result_schema=lambda _config: {
            "type": "object",
            "properties": {"matches": {"type": "boolean"}},
            "required": ["matches"],
            "additionalProperties": False,
        },
        open=open_session,
        check_source=check_source,
        default_scoring='def score(result):\n    return {"correctness": int(result["matches"])}',
    )
)


register(
    MethodDefinition(
        id="llm_judge",
        version=1,
        label="LLM judge",
        config_model=JudgeConfig,
        result_schema=lambda config: config["schema"],
        open=open_judge,
        default_scoring='def score(result):\n    return {"correctness": int(result["correct"])}',
        resource="model_endpoint",
        resolver=resolve_judge,
        preflight=preflight_judge,
        validate_fields=validate_judge_fields,
        preview=preview_judge,
    )
)
