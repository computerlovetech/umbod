import argparse
import re
import sys
from pathlib import Path
from typing import List

from markdown_it import MarkdownIt
from markdown_it.token import Token

from check_module_readmes import find_module_readmes, validate_readme


MAX_DESCRIPTION_LENGTH = 160
INLINE_TEXT_TYPES = {"text", "code_inline", "em_open", "em_close", "strong_open", "strong_close", "softbreak"}
ENTRY_PREFIX_TYPES = ["list_item_open", "paragraph_open", "inline", "paragraph_close"]


def inline_text(tokens: List[Token]) -> str:
    return "".join(" " if token.type == "softbreak" else token.content for token in tokens)


def entry_issue(tokens: List[Token]) -> str:
    if not tokens or tokens[0].type != "link_open" or not tokens[0].attrGet("href"):
        return "bullet must start with a Markdown link"
    closing = next((index for index, token in enumerate(tokens) if token.type == "link_close"), 0)
    label = tokens[1:closing]
    if not label or any(token.type not in INLINE_TEXT_TYPES for token in label) or not inline_text(label).strip():
        return "link must have a non-empty text label"
    description_tokens = tokens[closing + 1:]
    if any(token.type not in INLINE_TEXT_TYPES for token in description_tokens):
        return "description must contain only text or inline formatting"
    suffix = inline_text(description_tokens)
    if not suffix or not suffix[0].isspace():
        return "link must be followed by a short description separated by whitespace"
    description = re.sub(r"^[—–:\-]\s*", "", suffix.strip()).strip()
    if not description:
        return "link must be followed by a non-empty description"
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return f"description exceeds {MAX_DESCRIPTION_LENGTH} characters ({len(description)})"
    return ""


def validate_body(content: str) -> List[str]:
    frontmatter_issue = validate_readme(content)
    if frontmatter_issue:
        return [frontmatter_issue]
    lines = content.splitlines()
    body_start = lines.index("---", 1) + 1
    tokens = MarkdownIt("commonmark").parse("\n".join(lines[body_start:]))
    issues: List[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        line = body_start + (token.map[0] if token.map else 0) + 1
        if token.type == "heading_open":
            index += 3
            continue
        if token.type == "bullet_list_open":
            index += 1
            continue
        if token.type == "bullet_list_close":
            index += 1
            continue
        if token.type == "list_item_close":
            index += 1
            continue
        entry = tokens[index:index + len(ENTRY_PREFIX_TYPES)]
        if token.type == "list_item_open" and [item.type for item in entry] == ENTRY_PREFIX_TYPES:
            issue = entry_issue(entry[2].children or [])
            if issue:
                issues.append(f"line {line}: {issue}")
            index += len(ENTRY_PREFIX_TYPES)
            continue
        issues.append(f"line {line}: only headings and bullets containing a link followed by a description are allowed ({token.type})")
        break
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="Check source module README body format.")
    parser.add_argument("repository", type=Path)
    repository = parser.parse_args().repository.resolve()
    if not repository.is_dir():
        parser.error(f"repository is not a directory: {repository}")
    failures: List[str] = []
    try:
        readmes = find_module_readmes(repository)
        for readme in readmes:
            try:
                issues = validate_body(readme.read_text(encoding="utf-8"))
            except (OSError, UnicodeError) as error:
                issues = [f"cannot read UTF-8 Markdown: {error}"]
            failures.extend(f"{readme.relative_to(repository)}: {issue}" for issue in issues)
        if not readmes:
            failures.append("No README.md files found beneath src directories; check the repository path.")
    except OSError as error:
        failures.append(f"Cannot scan source directories: {error}")
    if failures:
        sys.stderr.write("\n".join(failures) + "\n")
        return 1
    sys.stdout.write(f"Body format check passed for {len(readmes)} module READMEs.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
