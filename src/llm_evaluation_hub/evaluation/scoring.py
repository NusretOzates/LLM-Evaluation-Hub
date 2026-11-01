"""Constrained preprocessing and score contract validation."""

import math
from typing import Any

from llm_evaluation_hub.core.datasets.records import parse_json_value
from llm_evaluation_hub.evaluation.contracts import Metric
from llm_evaluation_hub.execution.python import PythonRunner


def preprocess(response: dict[str, Any], source: str | None) -> object:
    """Produce a candidate without exposing examples or reference data."""
    visible = {key: response.get(key) for key in ("content", "parsed", "tool_calls")}
    if source:
        with PythonRunner(source, "preprocess") as runner:
            return parse_json_value(runner.run(visible))
    if visible["content"] is None:
        raise ValueError("response content is null; provide a preprocessor")
    return visible["content"]


def validate_scores(value: object, metrics: list[Metric] | None = None) -> dict[str, int | float]:
    """Require a complete set of finite numeric scores within declared ranges."""
    if not isinstance(value, dict) or not value:
        raise ValueError("score must return a nonempty dictionary")
    scores: dict[str, int | float] = {}
    for key, number in value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("score names must be nonempty strings")
        if (
            isinstance(number, bool)
            or not isinstance(number, int | float)
            or (isinstance(number, float) and not math.isfinite(number))
        ):
            raise ValueError(f"score {key} must be a finite number")
        scores[key] = number
    if metrics is not None:
        declarations = {metric.name: metric for metric in metrics}
        if set(scores) != set(declarations):
            raise ValueError("score names must match declared metrics")
        for key, number in scores.items():
            metric = declarations[key]
            if (metric.minimum is not None and number < metric.minimum) or (
                metric.maximum is not None and number > metric.maximum
            ):
                raise ValueError(f"score {key} is outside its declared range")
    return scores


def score(
    result: dict[str, Any], source: str, metrics: list[Metric] | None = None
) -> dict[str, int | float]:
    """Execute scoring code with only the validated method result."""
    with PythonRunner(source, "score") as runner:
        return validate_scores(runner.run(result), metrics)
