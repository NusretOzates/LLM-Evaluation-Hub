"""Catalog routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel

from llm_evaluation_hub.api.schemas import (
    DatasetView,
    ExamplePage,
    TagBranch,
    TagNode,
    TagPaths,
    branch_tree,
    dataset_view,
    leaf_paths,
    normalize_tag_forest,
    tag_tree,
)
from llm_evaluation_hub.core.datasets.catalog import DatasetRepository

router = APIRouter()


def repository(request: Request) -> DatasetRepository:
    """Return the catalog bound to this app."""
    catalog = request.app.state.repository
    if not isinstance(catalog, DatasetRepository):
        raise RuntimeError("catalog repository is not configured")
    return catalog


Catalog = Annotated[DatasetRepository, Depends(repository)]


@router.get("/health")
async def health() -> dict[str, str]:
    """Report process health without reading the catalog."""
    return {"status": "ok"}


@router.get("/tags")
def list_tags(catalog: Catalog) -> dict[str, TagNode]:
    """Return the tag forest."""
    return tag_tree(catalog.list_tags())


@router.post("/tags", status_code=201)
def create_tags(
    body: dict[str, TagBranch],
    catalog: Catalog,
    response: Response,
) -> dict[str, TagNode]:
    """Ensure every node in a tag forest and return that forest with stored paths."""
    forest = normalize_tag_forest(body)
    created = catalog.ensure_paths(leaf_paths(forest))
    if not created:
        response.status_code = 200
    return branch_tree(forest)


class TagDeletion(BaseModel):
    """Requested tag deletion mode."""

    path: str
    promote_children: bool = False


@router.get("/tag-impact")
def tag_impact(path: str, catalog: Catalog) -> dict[str, list[str] | int]:
    """Describe a tag subtree and its distinct affected dataset count."""
    paths, count = catalog.tag_impact(path)
    return {"paths": paths, "dataset_count": count}


@router.post("/tag-deletion", status_code=204)
def delete_tag(body: TagDeletion, catalog: Catalog) -> None:
    """Remove tags or promote children without deleting datasets."""
    catalog.delete_tag(body.path, promote_children=body.promote_children)


@router.get("/trash")
def list_trash(catalog: Catalog) -> list[DatasetView]:
    """List datasets retained in trash."""
    return [dataset_view(record) for record in catalog.list_trash()]


@router.post("/trash/{dataset_id}", status_code=204)
def trash_dataset(dataset_id: str, catalog: Catalog) -> None:
    """Move a dataset into trash."""
    catalog.trash(dataset_id)


@router.post("/trash/{dataset_id}/restore", status_code=204)
def restore_dataset(dataset_id: str, catalog: Catalog) -> None:
    """Restore a retained dataset."""
    catalog.restore(dataset_id)


@router.delete("/trash/{dataset_id}", status_code=204)
def purge_dataset(dataset_id: str, catalog: Catalog) -> None:
    """Permanently remove a dataset in trash."""
    catalog.purge(dataset_id)


@router.get("/datasets")
def list_datasets(catalog: Catalog, tag: str | None = None) -> list[DatasetView]:
    """Return dataset metadata, optionally limited to one tag subtree."""
    return [dataset_view(record) for record in catalog.list_datasets(tag=tag)]


@router.get("/dataset-ids/{dataset_id}")
def get_dataset_by_id(dataset_id: str, catalog: Catalog) -> DatasetView:
    """Return metadata by immutable ID."""
    return dataset_view(catalog.get_by_id(dataset_id))


@router.post("/dataset-ids/{dataset_id}/tags")
def add_tags_by_id(dataset_id: str, body: TagPaths, catalog: Catalog) -> DatasetView:
    """Link existing tags using a dataset's immutable identity."""
    return dataset_view(catalog.add_tags(catalog.get_by_id(dataset_id).name, body.paths))


@router.delete("/dataset-ids/{dataset_id}/tags")
def remove_tags_by_id(dataset_id: str, body: TagPaths, catalog: Catalog) -> DatasetView:
    """Unlink existing tags using a dataset's immutable identity."""
    return dataset_view(catalog.remove_tags(catalog.get_by_id(dataset_id).name, body.paths))


@router.get("/dataset-ids/{dataset_id}/examples")
def examples_by_id(
    dataset_id: str,
    catalog: Catalog,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ExamplePage:
    """Return a snapshot page by immutable ID."""
    record = catalog.get_by_id(dataset_id)
    return ExamplePage(
        total=record.rows_kept,
        offset=offset,
        limit=limit,
        examples=catalog.examples(record.name, offset=offset, limit=limit),
    )
