"""Literal judge prompt interpolation without expression evaluation."""

import json
import re
from typing import Any

from llm_evaluation_hub.core.datasets.records import parse_json_value

_PLACEHOLDER = re.compile(r"{{\s*([^{}]+?)\s*}}")


def validate_fields(template: str, allowed: set[str]) -> None:
    """Reject unknown placeholders even when there are no eligible rows."""
    for match in _PLACEHOLDER.finditer(template):
        if match.group(1) not in allowed:
            raise ValueError(f"unknown prompt field: {match.group(1)}")


def render_prompt(template: str, values: dict[str, Any], allowed: set[str]) -> str:
    """Replace known fields once; never recursively interpret inserted text."""

    def substitute(match: re.Match[str]) -> str:
        path = match.group(1)
        if path not in allowed:
            raise ValueError(f"unknown prompt field: {path}")
        if path not in values or values[path] is None:
            raise ValueError(f"prompt field is missing: {path}")
        value = parse_json_value(values[path])
        return (
            value
            if isinstance(value, str)
            else json.dumps(
                value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        )

    return _PLACEHOLDER.sub(substitute, template)
