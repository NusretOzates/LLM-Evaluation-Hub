"""Catalog routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

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


@router.get("/datasets")
def list_datasets(catalog: Catalog, tag: str | None = None) -> list[DatasetView]:
    """Return dataset metadata, optionally limited to one tag subtree."""
    return [dataset_view(record) for record in catalog.list_datasets(tag=tag)]


@router.get("/datasets/{name}")
def get_dataset(name: str, catalog: Catalog) -> DatasetView:
    """Return one dataset."""
    return dataset_view(catalog.get(name))


@router.post("/datasets/{name}/tags")
def add_dataset_tags(name: str, body: TagPaths, catalog: Catalog) -> DatasetView:
    """Link existing tags to a dataset."""
    return dataset_view(catalog.add_tags(name, body.paths))


@router.delete("/datasets/{name}/tags")
def remove_dataset_tags(name: str, body: TagPaths, catalog: Catalog) -> DatasetView:
    """Remove tag links from a dataset."""
    return dataset_view(catalog.remove_tags(name, body.paths))


@router.get("/datasets/{name}/examples")
def list_examples(
    name: str,
    catalog: Catalog,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ExamplePage:
    """Return one page of stored rows."""
    record = catalog.get(name)
    return ExamplePage(
        total=record.rows_kept,
        offset=offset,
        limit=limit,
        examples=catalog.examples(name, offset=offset, limit=limit),
    )


@router.get("/dataset-ids/{dataset_id}")
def get_dataset_by_id(dataset_id: str, catalog: Catalog) -> DatasetView:
    """Return metadata by immutable ID. Name-based endpoints remain compatible."""
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
    return list_examples(catalog.get_by_id(dataset_id).name, catalog, offset, limit)
