"""Errors raised by the dataset catalog."""


class CatalogError(Exception):
    """A catalog operation could not be completed."""


class DuplicateDatasetError(CatalogError):
    """A dataset name is already registered."""

    def __init__(self, name: str) -> None:
        """Name the dataset that already exists."""
        self.name = name
        super().__init__(
            f"dataset already exists: {name}. If it is in Trash, "
            "restore or permanently delete it first."
        )


class UnknownDatasetError(CatalogError):
    """No dataset is registered under this name."""

    def __init__(self, name: str) -> None:
        """Name the missing dataset."""
        self.name = name
        super().__init__(f"unknown dataset: {name}")


class DuplicateTagError(CatalogError):
    """A tag path is already present under the same parent."""

    def __init__(self, path: str) -> None:
        """Name the tag path that already exists."""
        self.path = path
        super().__init__(f"tag already exists: {path}")


class UnknownTagError(CatalogError):
    """No tag exists at this path."""

    def __init__(self, path: str) -> None:
        """Name the missing tag path."""
        self.path = path
        super().__init__(f"unknown tag: {path}")


class TagInUseError(CatalogError):
    """A tag still has a child tag or a dataset link."""

    def __init__(self, path: str) -> None:
        """Name the tag that cannot be deleted."""
        self.path = path
        super().__init__(f"tag is in use: {path}")
