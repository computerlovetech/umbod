import argparse
import sys
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

INDEX_PATH = Path("umbod/frontend/COMPONENT_INDEX.md")


class HtmlDestinations(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.destinations.extend(value for name, value in attrs if name in {"href", "src"} and value)


def token_destinations(tokens: list[Token]) -> Iterator[str]:
    for token in tokens:
        if token.type in {"link_open", "image"}:
            destination = token.attrGet("href" if token.type == "link_open" else "src")
            if destination:
                yield destination
        if token.type in {"html_inline", "html_block"}:
            parser = HtmlDestinations()
            parser.feed(token.content)
            yield from parser.destinations
        if token.children:
            yield from token_destinations(token.children)


def local_destinations(content: str) -> list[str]:
    destinations = token_destinations(MarkdownIt("commonmark").parse(content))
    return sorted({
        unquote(parsed.path)
        for destination in destinations
        if not (parsed := urlsplit(destination)).scheme and not parsed.netloc and parsed.path
    })


def check_index(repository: Path) -> list[str]:
    index = repository / INDEX_PATH
    try:
        destinations = local_destinations(index.read_text(encoding="utf-8"))
        if not destinations:
            return [f"{INDEX_PATH}: no local file links found"]
        failures: list[str] = []
        for destination in destinations:
            target = repository / destination.lstrip("/") if destination.startswith("/") else index.parent / destination
            if not target.exists():
                failures.append(f"{INDEX_PATH}: missing local target: {destination}")
        return failures
    except (OSError, UnicodeError, ValueError) as error:
        return [f"{INDEX_PATH}: cannot check links: {error}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail on dead local links in the frontend component index.")
    parser.add_argument("repository", type=Path)
    repository = parser.parse_args().repository.resolve()
    if not repository.is_dir():
        parser.error(f"repository is not a directory: {repository}")
    failures = check_index(repository)
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"Component index link check passed: {INDEX_PATH}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
