"""Validated transport and service contracts for local dataset imports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from llm_evaluation_hub.core.datasets.records import JsonValue, ProcessedExample
from llm_evaluation_hub.inference.contracts import OutputFormat

PROCESSOR_CONTRACT_VERSION: Literal["2"] = "2"
RUNTIME_POLICY_VERSION: Literal["1"] = "1"
MAX_ROWS = 10_000
SAMPLE_ROWS = 10


class ImportModel(BaseModel):
    """Reject unknown fields at import HTTP and persisted-specification boundaries."""

    model_config = ConfigDict(extra="forbid")


class SourceSpec(ImportModel):
    """Coordinates for the first supported source adapter."""

    kind: Literal["hf_dataset"] = "hf_dataset"
    repo_id: str = Field(min_length=1)
    config: str | None = None
    split: str = "train"
    revision: str = "main"

    @field_validator("repo_id")
    @classmethod
    def hub_identifier(cls, value: str) -> str:
        """Accept Hub repository IDs rather than local paths or loader URLs."""
        from huggingface_hub.utils import validate_repo_id

        validate_repo_id(value)
        if value.startswith(".") or ":" in value or "\\" in value:
            raise ValueError("Use a Hugging Face dataset repository ID.")
        return value

    @field_validator("split")
    @classmethod
    def plain_split(cls, value: str) -> str:
        """Keep row-prefix selection under the import service's control."""
        if not value or any(char in value for char in "[]:/\\") or value != value.strip():
            raise ValueError("Use a plain split name such as train.")
        return value

    @field_validator("revision")
    @classmethod
    def nonempty_revision(cls, value: str) -> str:
        """Require a named revision or commit rather than ambiguous blank input."""
        if not value.strip():
            raise ValueError("Revision must not be empty.")
        return value


class Diagnostic(ImportModel):
    """Safe source, processor, and operation failure information."""

    category: str
    message: str
    source_index: int | None = None
    line: int | None = None
    column: int | None = None
    field_path: str | None = None


class SampleRequest(ImportModel):
    """Load a bounded source prefix before authoring processor code."""

    source: SourceSpec
    row_limit: int = Field(default=MAX_ROWS, ge=1, le=MAX_ROWS)


class SourceColumn(ImportModel):
    """Observed top-level column types in a source sample."""

    name: str
    types: list[str]


class SampleView(ImportModel):
    """A transient raw sample pinned to one source commit."""

    id: str
    source: SourceSpec
    resolved_sha: str
    row_limit: int
    rows: list[dict[str, JsonValue]]
    columns: list[SourceColumn]
    expires_at: datetime


class PreviewRequest(ImportModel):
    """Execute a processor against an existing bounded source sample."""

    sample_id: str
    source_code: str = Field(min_length=1, max_length=65_536)


class PreviewRow(ImportModel):
    """One retained, intentionally dropped, or failed sample row."""

    source_index: int
    status: Literal["kept", "skipped", "failed"]
    example: ProcessedExample | None = None
    error: Diagnostic | None = None


class PreviewView(ImportModel):
    """Sample execution result and optional successful import attestation."""

    id: str | None = None
    sample_id: str
    resolved_sha: str
    source_hash: str
    rows: list[PreviewRow]
    rows_kept: int
    rows_dropped: int
    valid: bool
    expires_at: datetime


class ImportSpec(ImportModel):
    """Complete immutable execution specification copied into each accepted job."""

    source: SourceSpec
    row_limit: int = Field(ge=1, le=MAX_ROWS)
    resolved_sha: str
    source_code: str
    source_hash: str
    segment_keys: list[str]
    tags: list[str] = Field(default_factory=list)
    output_format: OutputFormat = Field(default_factory=OutputFormat)
    processor_contract_version: Literal["2"]
    runtime_policy_version: Literal["1"]
    runtime_version: str


class CreateImportRequest(ImportModel):
    """Name a validated execution and prevent duplicate browser submissions."""

    preview_id: str
    name: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    output_format: OutputFormat = Field(default_factory=OutputFormat)
    idempotency_key: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def catalog_name(cls, value: str) -> str:
        """Normalize surrounding form whitespace before catalog checks."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("Dataset name must not be empty.")
        return normalized


JobState = Literal[
    "queued", "running", "cancelling", "succeeded", "failed", "cancelled", "interrupted"
]


class JobView(ImportModel):
    """Public durable state without internal staging identities or credentials."""

    id: str
    name: str
    state: JobState
    phase: str
    rows_loaded: int
    rows_kept: int
    rows_dropped: int
    created_at: datetime
    updated_at: datetime
    dataset_id: str | None = None
    error: Diagnostic | None = None
    spec: ImportSpec


class JobList(ImportModel):
    """Jobs available for local workbench rediscovery."""

    jobs: list[JobView]


class SourceChoice(ImportModel):
    """An enabled source adapter presented by the UI selector."""

    kind: Literal["hf_dataset"] = "hf_dataset"
    label: str = "Hugging Face"


class ImportLimits(ImportModel):
    """Public form limits owned by the trusted server policy."""

    max_rows: int = MAX_ROWS
    sample_rows: int = SAMPLE_ROWS
    max_source_bytes: int = 65_536


class SourcesView(ImportModel):
    """Enabled source capabilities and effective request limits."""

    sources: list[SourceChoice] = Field(default_factory=lambda: [SourceChoice()])
    limits: ImportLimits = Field(default_factory=ImportLimits)


class ProcessorView(ImportModel):
    """Optional stored processor provenance for an immutable dataset snapshot."""

    provenance: dict[str, JsonValue] | None
