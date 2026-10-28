"""Request and response models for the catalog API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from llm_evaluation_hub.core.datasets.catalog import DatasetRecord, Tag
from llm_evaluation_hub.core.datasets.records import ProcessedExample


class InvalidRequestError(ValueError):
    """A semantically invalid client request, distinct from stored-data failures."""


class TagBranch(BaseModel):
    """One node in a tag forest sent by a client."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    children: dict[str, "TagBranch"] = Field(default_factory=dict)


class TagNode(BaseModel):
    """One node in the tag forest returned to a client."""

    model_config = ConfigDict(extra="forbid")

    path: str
    children: dict[str, "TagNode"] = Field(default_factory=dict)


class TagPaths(BaseModel):
    """Tag paths to link or unlink."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(min_length=1)


class DatasetView(BaseModel):
    """Dataset metadata a client can show."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    created_at: datetime
    processor_id: str
    source_type: str
    repo_id: str | None
    config: str | None
    split: str | None
    revision: str | None
    resolved_sha: str | None
    row_limit: int | None
    rows_loaded: int
    rows_kept: int
    rows_dropped: int
    segment_keys: list[str]
    tags: list[str]


class ExamplePage(BaseModel):
    """One page of stored dataset rows."""

    model_config = ConfigDict(extra="forbid")

    total: int
    offset: int
    limit: int
    examples: list[ProcessedExample]


def normalize_tag_forest(forest: dict[str, TagBranch]) -> dict[str, TagBranch]:
    """Strip tag names and reject an empty forest or an illegal name."""
    if not forest:
        raise InvalidRequestError("tag forest must not be empty")
    return _normalize_level(forest)


def leaf_paths(forest: dict[str, TagBranch], prefix: list[str] | None = None) -> list[list[str]]:
    """Return one segment list for each leaf, in name order."""
    segments_so_far = [] if prefix is None else prefix
    paths: list[list[str]] = []
    for name in sorted(forest):
        branch = forest[name]
        segments = [*segments_so_far, name]
        expected = "/".join(segments)
        if branch.path is not None and branch.path != expected:
            raise InvalidRequestError("tag path does not match its place in the tree")
        if branch.children:
            paths.extend(leaf_paths(branch.children, segments))
        else:
            paths.append(segments)
    return paths


def branch_tree(forest: dict[str, TagBranch], parent: str | None = None) -> dict[str, TagNode]:
    """Fill stored paths for a forest the client submitted."""
    rendered: dict[str, TagNode] = {}
    for name in sorted(forest):
        path = name if parent is None else f"{parent}/{name}"
        rendered[name] = TagNode(path=path, children=branch_tree(forest[name].children, path))
    return rendered


def _normalize_level(forest: dict[str, TagBranch]) -> dict[str, TagBranch]:
    """Return one level with stripped names."""
    normalized: dict[str, TagBranch] = {}
    for raw_name, branch in forest.items():
        name = raw_name.strip()
        if name == "" or "/" in name:
            raise InvalidRequestError("tag name must not be empty or contain '/'")
        if name in normalized:
            raise InvalidRequestError(f"duplicate tag name: {name}")
        normalized[name] = TagBranch(path=branch.path, children=_normalize_level(branch.children))
    return normalized


def tag_tree(tags: list[Tag]) -> dict[str, TagNode]:
    """Build a name-keyed forest from path-ordered tag rows."""
    nodes = {tag.path: TagNode(path=tag.path) for tag in tags}
    roots: dict[str, TagNode] = {}
    for tag in tags:
        node = nodes[tag.path]
        if tag.parent is None:
            roots[tag.name] = node
            continue
        nodes[tag.parent].children[tag.name] = node
    return roots


def dataset_view(record: DatasetRecord) -> DatasetView:
    """Project a catalog record without its storage path."""
    return DatasetView.model_validate(
        record.model_dump(exclude={"parquet_path", "snapshot_format_version"})
    )


TagBranch.model_rebuild()
TagNode.model_rebuild()
