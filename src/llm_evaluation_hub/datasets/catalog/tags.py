"""Tag forest stored in the catalog database."""

import sqlite3
import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from llm_evaluation_hub.datasets.catalog.errors import (
    DuplicateTagError,
    TagInUseError,
    UnknownTagError,
)


class Tag(BaseModel):
    """One node in the tag forest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parent: str | None
    path: str


class TagStore:
    """Create, link, and query tag nodes on an open catalog connection."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        """Use a connection whose transaction the caller owns."""
        self._connection = connection

    def create(self, name: str, parent: str | None = None) -> Tag:
        """Insert a tag. The parent path must already exist."""
        if name == "" or "/" in name:
            raise ValueError("tag name must not be empty or contain '/'")
        parent_id = None
        if parent is None:
            path = name
        else:
            parent_id = self.require(parent)["id"]
            path = f"{parent}/{name}"
        try:
            self._connection.execute(
                "INSERT INTO tags (id, name, parent_id, path) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), name, parent_id, path),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateTagError(path) from error
        return Tag(name=name, parent=parent, path=path)

    def require(self, path: str) -> sqlite3.Row:
        """Return the tag row or raise when the path is missing."""
        row = self._connection.execute("SELECT * FROM tags WHERE path = ?", (path,)).fetchone()
        if row is None:
            raise UnknownTagError(path)
        return row

    def delete(self, path: str) -> None:
        """Delete a tag that has no children and no dataset links."""
        row = self.require(path)
        child = self._connection.execute(
            "SELECT 1 FROM tags WHERE parent_id = ?",
            (row["id"],),
        ).fetchone()
        link = self._connection.execute(
            "SELECT 1 FROM dataset_tags WHERE tag_id = ?",
            (row["id"],),
        ).fetchone()
        if child is not None or link is not None:
            raise TagInUseError(path)
        self._connection.execute("DELETE FROM tags WHERE id = ?", (row["id"],))

    def descendant_ids(self, path: str) -> list[str]:
        """Return the tag id and the ids of every tag below it."""
        rows = self._connection.execute("SELECT id, parent_id, path FROM tags").fetchall()
        by_path = {row["path"]: row["id"] for row in rows}
        if path not in by_path:
            raise UnknownTagError(path)
        children: dict[str, list[str]] = {}
        for row in rows:
            parent_id = row["parent_id"]
            if parent_id is not None:
                children.setdefault(parent_id, []).append(row["id"])
        found: list[str] = []
        stack = [by_path[path]]
        while stack:
            current = stack.pop()
            found.append(current)
            stack.extend(children.get(current, ()))
        return found

    def link(self, dataset_id: str, paths: Sequence[str]) -> None:
        """Insert dataset links. An existing link is left in place."""
        for path in paths:
            tag_id = self.require(path)["id"]
            self._connection.execute(
                "INSERT OR IGNORE INTO dataset_tags (dataset_id, tag_id) VALUES (?, ?)",
                (dataset_id, tag_id),
            )

    def unlink(self, dataset_id: str, paths: Sequence[str]) -> None:
        """Remove dataset links. A missing link is left absent."""
        for path in paths:
            tag_id = self.require(path)["id"]
            self._connection.execute(
                "DELETE FROM dataset_tags WHERE dataset_id = ? AND tag_id = ?",
                (dataset_id, tag_id),
            )

    def paths_for(self, dataset_id: str) -> list[str]:
        """Return the tag paths linked directly to a dataset, in path order."""
        rows = self._connection.execute(
            """
            SELECT tags.path
            FROM dataset_tags
            JOIN tags ON tags.id = dataset_tags.tag_id
            WHERE dataset_tags.dataset_id = ?
            ORDER BY tags.path
            """,
            (dataset_id,),
        ).fetchall()
        return [row["path"] for row in rows]
