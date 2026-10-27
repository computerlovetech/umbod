import argparse
import os
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from check_module_readmes import EXCLUDED_DIRECTORIES, raise_walk_error


class HtmlLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        self.destinations.extend(value for name, value in attrs if name in {"href", "src"} and value)


def token_destinations(tokens: List[Token]) -> Iterator[str]:
    for token in tokens:
        if token.type in {"link_open", "image"}:
            destination = token.attrGet("href" if token.type == "link_open" else "src")
            if destination:
                yield destination
        if token.type in {"html_inline", "html_block"}:
            parser = HtmlLinks()
            parser.feed(token.content)
            yield from parser.destinations
        if token.children:
            yield from token_destinations(token.children)


def local_destinations(content: str) -> List[str]:
    destinations = token_destinations(MarkdownIt("commonmark").parse(content))
    return sorted({
        unquote(parsed.path)
        for destination in destinations
        if not (parsed := urlsplit(destination)).scheme and not parsed.netloc and parsed.path
    })


def find_readmes(repository: Path) -> Iterator[Path]:
    for directory, children, filenames in os.walk(repository, onerror=raise_walk_error):
        children[:] = sorted(set(children) - EXCLUDED_DIRECTORIES)
        if "README.md" in filenames:
            yield Path(directory) / "README.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local file links in repository README.md files.")
    parser.add_argument("repository", type=Path)
    repository = parser.parse_args().repository.resolve()
    if not repository.is_dir():
        parser.error(f"repository is not a directory: {repository}")
    failures: List[str] = []
    count = 0
    try:
        for readme in find_readmes(repository):
            count += 1
            try:
                destinations = local_destinations(readme.read_text(encoding="utf-8"))
                for destination in destinations:
                    target = repository / destination.lstrip("/") if destination.startswith("/") else readme.parent / destination
                    if not target.exists():
                        failures.append(f"{readme.relative_to(repository)}: missing local target: {destination}")
            except (OSError, UnicodeError, ValueError) as error:
                failures.append(f"{readme.relative_to(repository)}: cannot check links: {error}")
    except OSError as error:
        failures.append(f"Cannot scan README.md files: {error}")
    if not count:
        failures.append("No README.md files found; check the repository path.")
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"Local link check passed for {count} README.md files.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
