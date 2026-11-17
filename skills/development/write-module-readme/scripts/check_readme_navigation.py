import argparse
import sys
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from check_readme_links import find_readmes
from markdown_it import MarkdownIt
from markdown_it.token import Token


class HtmlNavigationLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.destinations: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.destinations.extend(value for name, value in attrs if name == "href" and value)


def navigation_destinations(tokens: list[Token]) -> Iterator[str]:
    for token in tokens:
        if token.type == "link_open":
            destination = token.attrGet("href")
            if destination:
                yield destination
        if token.type in {"html_inline", "html_block"}:
            parser = HtmlNavigationLinks()
            parser.feed(token.content)
            yield from parser.destinations
        if token.children and token.type != "image":
            yield from navigation_destinations(token.children)


def local_navigation(content: str) -> list[str]:
    destinations = navigation_destinations(MarkdownIt("commonmark").parse(content))
    return sorted({
        unquote(parsed.path)
        for destination in destinations
        if not (parsed := urlsplit(destination)).scheme and not parsed.netloc and parsed.path
    })


def navigation_failures(repository: Path, entrypoints: list[Path]) -> list[str]:
    readmes = {path.resolve() for path in find_readmes(repository)}
    source_readmes = {
        path for path in readmes
        if path.is_relative_to(repository) and "src" in path.relative_to(repository).parts
    }
    failures: list[str] = []
    if not source_readmes:
        failures.append("No README.md files found beneath src directories; check the repository path.")
    valid_entrypoints: set[Path] = set()
    for entrypoint in entrypoints:
        if not entrypoint.is_relative_to(repository):
            failures.append(f"navigation entrypoint outside repository: {entrypoint}")
        elif not entrypoint.is_file():
            failures.append(f"missing navigation entrypoint: {entrypoint.relative_to(repository)}")
        else:
            valid_entrypoints.add(entrypoint)
    graph: dict[Path, set[Path]] = {}
    for document in sorted(readmes | valid_entrypoints):
        if not document.is_relative_to(repository):
            continue
        targets: set[Path] = set()
        for destination in local_navigation(document.read_text(encoding="utf-8")):
            target = (
                repository / destination.lstrip("/") if destination.startswith("/")
                else document.parent / destination
            ).resolve()
            if target in readmes:
                targets.add(target)
            if target.is_dir() and any(
                child.is_relative_to(target) for child in source_readmes
            ):
                failures.append(
                    f"{document.relative_to(repository)}: directory navigation hides README links: "
                    f"{destination}; link to the routing README or child READMEs explicitly"
                )
        graph[document] = targets
    reachable: set[Path] = set()
    pending = list(valid_entrypoints)
    while pending:
        document = pending.pop()
        if document not in reachable:
            reachable.add(document)
            pending.extend(graph.get(document, set()) - reachable)
    failures.extend(
        f"unreachable source README: {path.relative_to(repository)}; add an explicit link from a reachable index"
        for path in sorted(source_readmes - reachable)
    )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source README reachability and explicit module navigation.")
    parser.add_argument("repository", type=Path)
    parser.add_argument("--entrypoint", type=Path, action="append", help="Repository-relative navigation root; repeat to add roots. Defaults to AGENTS.md.")
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    if not repository.is_dir():
        parser.error("repository must be an existing directory")
    entrypoints = [(repository / path).resolve() for path in arguments.entrypoint or [Path("AGENTS.md")]]
    try:
        failures = navigation_failures(repository, entrypoints)
    except (OSError, UnicodeError, ValueError) as error:
        sys.stderr.write(f"Cannot check README navigation: {error}\n")
        return 1
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write("Source README navigation check passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
