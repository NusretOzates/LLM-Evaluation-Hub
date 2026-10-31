"""Validated, credential-free inference configuration and durable views."""

import re
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from llm_evaluation_hub.core.datasets.records import JsonValue

PROTECTED_FIELDS = frozenset(
    {
        "model",
        "messages",
        "tools",
        "response_format",
        "stream",
        "n",
        "max_tokens",
        "max_completion_tokens",
        "temperature",
        "top_p",
        "seed",
    }
)


class Contract(BaseModel):
    """Reject unknown configuration rather than silently ignoring it."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ConnectionProfile(Contract):
    """Connection settings; credentials are referenced only by environment name."""

    id: str = ""
    name: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_env: str | None = None
    reasoning_mode: Literal["effort", "thinking"] = "effort"
    effort_levels: list[str] = Field(default_factory=lambda: ["low", "medium", "high"])
    effort_path: str = "reasoning_effort"
    thinking_path: str = "thinking.enabled"
    max_tokens_field: Literal["max_completion_tokens", "max_tokens"] = "max_completion_tokens"

    @model_validator(mode="after")
    def validate_connection(self) -> Self:
        """Forbid embedded secrets and ambiguous environment references."""
        url = urlsplit(self.base_url)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("base URL must be an HTTP URL without credentials, query, or fragment")
        if self.api_key_env is not None and not re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env
        ):
            raise ValueError("API key environment reference must be an environment variable name")
        if self.reasoning_mode == "effort" and (
            not self.effort_levels
            or any(not level.strip() for level in self.effort_levels)
            or len(set(self.effort_levels)) != len(self.effort_levels)
        ):
            raise ValueError("effort levels must be non-empty and unique")
        path = self.effort_path if self.reasoning_mode == "effort" else self.thinking_path
        parts = path.split(".")
        if not all(parts) or parts[0] in PROTECTED_FIELDS:
            raise ValueError("reasoning path is invalid or conflicts with a protected field")
        return self


class OutputFormat(Contract):
    """Dataset output format and optional object-root JSON Schema."""

    kind: Literal["text", "json_object", "json_schema"] = "text"
    schema_: dict[str, JsonValue] | None = Field(
        default=None, alias="schema", serialization_alias="schema"
    )
    strict: bool = True

    @model_validator(mode="after")
    def require_schema(self) -> Self:
        """Schema output needs an object-root schema."""
        if self.kind == "json_schema" and (
            self.schema_ is None or self.schema_.get("type") != "object"
        ):
            raise ValueError("JSON Schema output requires an object-root schema")
        return self


class Generation(Contract):
    """Optional request controls."""

    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    effort: str | None = None
    thinking: bool | None = None
    advanced: dict[str, JsonValue] = Field(default_factory=dict)


class RunSpec(Contract):
    """User-selected run settings."""

    dataset_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    profile_id: str
    generation: Generation = Field(default_factory=Generation)
    output_overrides: dict[str, OutputFormat] = Field(default_factory=dict)
    concurrency: int = Field(default=4, ge=1, le=100)
    rpm: int = Field(default=60, ge=1)
    timeout_seconds: float = Field(default=120, gt=0)
    retries: int = Field(default=2, ge=0, le=10)


class RowResult(Contract):
    """A persisted result for one retained row."""

    dataset_id: str
    ordinal: int
    source_index: int
    status: str
    raw_response: JsonValue = None
    content: str | None = None
    tool_calls: JsonValue = None
    parsed: JsonValue = None
    validation_errors: list[str] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: JsonValue = None
    latency_ms: float | None = None
    attempts: int = 0
    error: str | None = None


class ResultPage(Contract):
    """A filtered page of persisted row results."""

    results: list[RowResult]
    total: int
    offset: int
    limit: int


class FrozenDataset(Contract):
    """Dataset identity, frozen output and durable progress."""

    id: str
    name: str
    snapshot_format_version: int
    rows: int
    output: OutputFormat
    completed: int
    errors: int
    input_available: bool


class RunView(Contract):
    """Persisted run metadata with frozen configuration."""

    id: str
    state: str
    error: str | None = None
    created_at: str
    updated_at: str
    spec: dict[str, JsonValue]
    completed: int
    total: int
    datasets: list[FrozenDataset] = Field(default_factory=list)
