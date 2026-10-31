"""Validate schemas and compile stored conversations into chat requests."""

import copy
import json
from typing import Any

from jsonschema import Draft202012Validator

from llm_evaluation_hub.core.datasets.records import ProcessedExample, message_payload
from llm_evaluation_hub.inference.contracts import (
    PROTECTED_FIELDS,
    ConnectionProfile,
    Generation,
    OutputFormat,
)


def validate_format(output: OutputFormat) -> None:
    """Validate a schema locally without resolving any external references."""
    if output.kind != "json_schema":
        return
    schema = output.schema_
    assert schema is not None
    Draft202012Validator.check_schema(schema)
    _check_schema(schema, output.strict)


def _check_schema(value: object, strict: bool) -> None:  # noqa: PLR0912
    if not isinstance(value, dict):
        return
    for key in ("$ref", "$dynamicRef"):
        ref = value.get(key)
        if isinstance(ref, str) and not ref.startswith("#"):
            raise ValueError("remote schema references are not supported")
    schema_type = value.get("type")
    if strict and (
        schema_type == "object" or (isinstance(schema_type, list) and "object" in schema_type)
    ):
        properties = value.get("properties", {})
        if not isinstance(properties, dict) or set(value.get("required", [])) != set(properties):
            raise ValueError("strict schemas require every property")
        if value.get("additionalProperties") is not False:
            raise ValueError("strict schemas require additionalProperties=false")
    for key in ("properties", "$defs", "definitions", "patternProperties", "dependentSchemas"):
        children = value.get(key)
        if isinstance(children, dict):
            for child in children.values():
                _check_schema(child, strict)
    for key in (
        "items",
        "additionalProperties",
        "not",
        "if",
        "then",
        "else",
        "contains",
        "propertyNames",
        "unevaluatedProperties",
        "unevaluatedItems",
    ):
        _check_schema(value.get(key), strict)
    for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
        children = value.get(key)
        if isinstance(children, list):
            for child in children:
                _check_schema(child, strict)


def _set_path(body: dict[str, Any], path: str, value: object) -> None:
    parts = path.split(".")
    if not all(parts):
        raise ValueError("request body paths must contain non-empty segments")
    current = body
    for part in parts[:-1]:
        child = current.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"conflicting request field: {path}")
        current = child
    if parts[-1] in current:
        raise ValueError(f"conflicting request field: {path}")
    current[parts[-1]] = value


def compile_request(  # noqa: C901, PLR0912
    profile: ConnectionProfile,
    generation: Generation,
    output: OutputFormat,
    example: ProcessedExample,
) -> dict[str, Any]:
    """Compile one request without including gold data, extras, or credentials."""
    validate_format(output)
    body: dict[str, Any] = copy.deepcopy(generation.advanced)
    protected = PROTECTED_FIELDS
    if protected.intersection(body):
        raise ValueError("advanced parameters conflict with protected or common fields")
    messages = []
    for message in example.conversation:
        payload = message_payload(message)
        if payload.get("thinking") is not None:
            raise ValueError("historical thinking is not supported")
        content = payload.get("content")
        if isinstance(content, list) and any(part.get("type") != "text" for part in content):
            raise ValueError("media inputs are not supported")
        calls = payload.get("tool_calls", [])
        assert isinstance(calls, list)
        for call in calls:
            call["function"]["arguments"] = json.dumps(
                call["function"]["arguments"], ensure_ascii=False, separators=(",", ":")
            )
        messages.append(payload)
    body.update(model=profile.model, messages=messages, stream=False, n=1)
    if example.tools:
        body["tools"] = [tool.model_dump(mode="json", exclude_none=True) for tool in example.tools]
    for field in ("temperature", "top_p", "seed"):
        value = getattr(generation, field)
        if value is not None:
            body[field] = value
    if generation.max_tokens is not None:
        body[profile.max_tokens_field] = generation.max_tokens
    if generation.effort is not None:
        if profile.reasoning_mode != "effort" or generation.effort not in profile.effort_levels:
            raise ValueError("unsupported reasoning effort")
        _set_path(body, profile.effort_path, generation.effort)
    if generation.thinking is not None:
        if profile.reasoning_mode != "thinking":
            raise ValueError("thinking control is not supported")
        _set_path(body, profile.thinking_path, generation.thinking)
    if output.kind == "json_object":
        body["response_format"] = {"type": "json_object"}
    elif output.kind == "json_schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "output", "strict": output.strict, "schema": output.schema_},
        }
    return body
