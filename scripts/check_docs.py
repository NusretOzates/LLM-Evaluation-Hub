"""Check local Markdown links and OKF concept frontmatter independently."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)]+)\)")


def main() -> None:
    """Fail on missing local file targets or invalid concept YAML/type fields."""
    failures: list[str] = []
    documents = sorted((ROOT / "docs").rglob("*.md"))
    for path in [ROOT / "README.md", ROOT / "web/README.md", *documents]:
        text = path.read_text(encoding="utf-8")
        if path in documents and path.name not in {"index.md", "glossary.md", "log.md"}:
            try:
                if not text.startswith("---\n"):
                    raise ValueError("missing frontmatter")
                header = yaml.safe_load(text.split("---", 2)[1])
                if (
                    not isinstance(header, dict)
                    or not isinstance(header.get("type"), str)
                    or not header["type"].strip()
                ):
                    raise ValueError("missing nonempty concept type")
            except (ValueError, yaml.YAMLError) as error:
                failures.append(f"{path.relative_to(ROOT)}: frontmatter: {error}")
        for match in LINK.finditer(text):
            target = match.group(1).split(' "', 1)[0].strip("<>")
            parts = urlsplit(target)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            relative = unquote(parts.path)
            resolved = (
                (ROOT / "docs" / relative.lstrip("/"))
                if relative.startswith("/")
                else path.parent / relative
            )
            if not resolved.is_file():
                failures.append(f"{path.relative_to(ROOT)}: missing link target: {target}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(
        f"Documentation checks passed ({len(documents)} bundle documents; "
        "file targets and concept frontmatter)."
    )


if __name__ == "__main__":
    main()
