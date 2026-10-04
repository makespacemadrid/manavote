"""Repository-level checks that keep the documentation navigable and complete."""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
MARKDOWN_LINK = re.compile(r"\[[^]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*$")


def _markdown_files() -> list[Path]:
    return [ROOT / "README.md", *sorted(DOCS.rglob("*.md"))]


def _slug(value: str) -> str:
    """Approximate GitHub's generated heading IDs for repository-local links."""

    normalized = re.sub(r"[^\w\- ]", "", value.strip().lower())
    return normalized.replace(" ", "-")


def _local_links(path: Path) -> list[tuple[int, str, str]]:
    links = []
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        for raw_target in MARKDOWN_LINK.findall(line):
            file_target, separator, fragment = raw_target.partition("#")
            if "://" in file_target or file_target.startswith("/"):
                continue
            links.append((line_number, file_target, fragment if separator else ""))
    return links


def test_relative_markdown_links_and_fragments_resolve():
    failures = []
    for source in _markdown_files():
        for line_number, file_target, fragment in _local_links(source):
            target = (source.parent / file_target).resolve() if file_target else source
            if not target.is_file():
                failures.append(f"{source.relative_to(ROOT)}:{line_number}: missing {file_target}")
                continue
            if fragment:
                headings = {
                    _slug(match.group(1))
                    for line in target.read_text().splitlines()
                    if (match := HEADING.match(line))
                }
                if fragment not in headings:
                    failures.append(
                        f"{source.relative_to(ROOT)}:{line_number}: "
                        f"missing #{fragment} in {target.relative_to(ROOT)}"
                    )
    assert not failures, "\n".join(failures)


def test_every_document_is_reachable_from_the_documentation_map():
    entry = DOCS / "INDEX.md"
    reachable = {entry.resolve()}
    queue = deque([entry])

    while queue:
        source = queue.popleft()
        for _, file_target, _ in _local_links(source):
            if not file_target:
                continue
            target = (source.parent / file_target).resolve()
            if target.suffix == ".md" and DOCS.resolve() in target.parents and target not in reachable:
                reachable.add(target)
                queue.append(target)

    expected = {path.resolve() for path in DOCS.rglob("*.md")}
    missing = sorted(str(path.relative_to(ROOT)) for path in expected - reachable)
    assert not missing, f"Documentation not reachable from docs/INDEX.md: {missing}"


def test_sample_environment_variables_are_documented():
    variables = set(
        re.findall(
            r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=",
            (ROOT / "sample.env").read_text(),
            re.MULTILINE,
        )
    )
    quickstart = (DOCS / "QUICKSTART.md").read_text()
    missing = sorted(variable for variable in variables if f"`{variable}`" not in quickstart)
    assert not missing, f"Environment variables missing from QUICKSTART.md: {missing}"
