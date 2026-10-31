"""Tag forest stored in the catalog database."""

import sqlite3
import uuid
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from llm_evaluation_hub.core.datasets.catalog.errors import (
    DuplicateTagError,
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
        parent_id, path = self._location(name, parent)
        try:
            self._connection.execute(
                "INSERT INTO tags (id, name, parent_id, path) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), name, parent_id, path),
            )
        except sqlite3.IntegrityError as error:
            raise DuplicateTagError(path) from error
        return Tag(name=name, parent=parent, path=path)

    def ensure(self, name: str, parent: str | None = None) -> tuple[Tag, bool]:
        """Return a tag node, inserting it when the path is absent."""
        parent_id, path = self._location(name, parent)
        if self._path_exists(path):
            return Tag(name=name, parent=parent, path=path), False
        try:
            self._connection.execute(
                "INSERT INTO tags (id, name, parent_id, path) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), name, parent_id, path),
            )
        except sqlite3.IntegrityError:
            if not self._path_exists(path):
                raise
            return Tag(name=name, parent=parent, path=path), False
        return Tag(name=name, parent=parent, path=path), True

    def list_tags(self) -> list[Tag]:
        """Return every tag, ordered by path."""
        rows = self._connection.execute(
            """
            SELECT child.name AS name, child.path AS path, parent.path AS parent
            FROM tags AS child
            LEFT JOIN tags AS parent ON parent.id = child.parent_id
            ORDER BY child.path
            """
        ).fetchall()
        return [Tag(name=row["name"], parent=row["parent"], path=row["path"]) for row in rows]

    def _location(self, name: str, parent: str | None) -> tuple[str | None, str]:
        """Validate a segment and return the parent id and stored path."""
        if name == "" or "/" in name:
            raise ValueError("tag name must not be empty or contain '/'")
        if parent is None:
            return None, name
        parent_id = self.require(parent)["id"]
        return str(parent_id), f"{parent}/{name}"

    def _path_exists(self, path: str) -> bool:
        """Report whether a tag path is already stored."""
        row = self._connection.execute("SELECT 1 FROM tags WHERE path = ?", (path,)).fetchone()
        return row is not None

    def require(self, path: str) -> sqlite3.Row:
        """Return the tag row or raise when the path is missing."""
        row = self._connection.execute("SELECT * FROM tags WHERE path = ?", (path,)).fetchone()
        if row is None:
            raise UnknownTagError(path)
        return row

    def impact(self, path: str) -> tuple[list[str], int]:
        """Return subtree paths and the number of distinct linked datasets."""
        ids = self.descendant_ids(path)
        marks = ", ".join("?" for _ in ids)
        rows = self._connection.execute(
            f"SELECT path FROM tags WHERE id IN ({marks}) ORDER BY path", ids
        ).fetchall()
        count = self._connection.execute(
            f"SELECT COUNT(DISTINCT dataset_id) FROM dataset_tags WHERE tag_id IN ({marks})", ids
        ).fetchone()[0]
        return [row["path"] for row in rows], count

    def delete(self, path: str, *, promote_children: bool = False) -> None:
        """Delete a subtree or promote its children while preserving their identities."""
        row = self.require(path)
        ids = self.descendant_ids(path)
        if promote_children:
            descendants = self._connection.execute(
                "SELECT id, path FROM tags WHERE path LIKE ? ESCAPE '\\' ORDER BY length(path)",
                (path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%",),
            ).fetchall()
            parent = path.rpartition("/")[0]
            replacements = [
                (item["id"], (parent + "/" if parent else "") + item["path"][len(path) + 1 :])
                for item in descendants
            ]
            for _, destination in replacements:
                existing = self._connection.execute(
                    "SELECT id FROM tags WHERE path = ?", (destination,)
                ).fetchone()
                if existing is not None and existing["id"] not in ids:
                    raise DuplicateTagError(destination)
            self._connection.execute("DELETE FROM dataset_tags WHERE tag_id = ?", (row["id"],))
            self._connection.execute(
                "UPDATE tags SET parent_id = ? WHERE parent_id = ?", (row["parent_id"], row["id"])
            )
            self._connection.execute("DELETE FROM tags WHERE id = ?", (row["id"],))
            for tag_id, _ in replacements:
                self._connection.execute(
                    "UPDATE tags SET path = ? WHERE id = ?", (f"/__moving__/{uuid.uuid4()}", tag_id)
                )
            for tag_id, destination in replacements:
                self._connection.execute(
                    "UPDATE tags SET path = ? WHERE id = ?", (destination, tag_id)
                )
        else:
            marks = ", ".join("?" for _ in ids)
            self._connection.execute(f"DELETE FROM dataset_tags WHERE tag_id IN ({marks})", ids)
            for tag_id in reversed(ids):
                self._connection.execute("DELETE FROM tags WHERE id = ?", (tag_id,))

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
