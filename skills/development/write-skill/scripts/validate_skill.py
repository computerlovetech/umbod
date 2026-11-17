import argparse
import re
import sys
from pathlib import Path

DEFAULT_MAX_CHARS = 6000
SECTION_NAMES = (
    "Outcome",
    "Inputs",
    "Rules",
    "Workflow",
    "Decisions",
    "Output",
    "Completion criteria",
    "References",
)
FRONTMATTER = re.compile(
    r"\A---\nname: ([a-z]+(?:-[a-z]+)+)\n"
    r"description: >\n((?:  \S[^\n]*\n)+)---\n\n"
)
PLACEHOLDER = re.compile(r"\[[^\]\n]+\](?!\()")
LOCAL_RESOURCE = re.compile(r"(?<![\w/])(?:references|scripts)/[\w./-]+")
REFERENCE = re.compile(
    r"- (?:Read `(references/[^`]+)` when|Run `(scripts/[^`]+)` to) .+"
)


def matches_lines(lines: list[str], patterns: list[str]) -> bool:
    return len(lines) == len(patterns) and all(
        re.fullmatch(pattern, line) for pattern, line in zip(patterns, lines)
    )


def validate_skill(content: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    errors: list[str] = []
    if max_chars < 1:
        return ["Character budget must be positive."]
    if len(content) > max_chars:
        errors.append(f"Character count {len(content)} exceeds limit {max_chars}.")
    if "\r" in content or not content.endswith("\n"):
        errors.append("Use LF line endings and a final newline.")
    if PLACEHOLDER.search(content):
        errors.append("Replace all bracketed template placeholders.")
    frontmatter = FRONTMATTER.match(content)
    if frontmatter is None:
        return errors + [
            "Use exactly name: verb-noun and description: > frontmatter from the template."
        ]
    description = " ".join(line.strip() for line in frontmatter[2].splitlines())
    if not re.search(r"\S.*\. Use when \S", description):
        errors.append(
            "Description must state a capability followed by '. Use when ' and a trigger."
        )
    body = content[frontmatter.end() :]
    lines = body.splitlines()
    if not lines or not re.fullmatch(r"# [^#\s].*", lines[0]):
        errors.append("Start the body with one '# Skill title' heading.")
    headings = [line for line in lines if re.match(r" {0,3}#", line)]
    expected = [lines[0] if lines else ""] + [f"## {name}" for name in SECTION_NAMES]
    if headings != expected:
        return errors + [
            "Headings must be one title followed by: "
            + ", ".join(SECTION_NAMES)
            + "; no extra headings."
        ]
    if len(lines) < 3 or lines[1] != "" or lines[2] != "## Outcome":
        errors.append(
            "Separate the title from Outcome with one blank line and no introductory text."
        )
    sections: dict[str, list[str]] = {}
    for index, name in enumerate(SECTION_NAMES):
        start = lines.index(f"## {name}") + 1
        end = (
            lines.index(f"## {SECTION_NAMES[index + 1]}")
            if index + 1 < len(SECTION_NAMES)
            else len(lines)
        )
        section = lines[start:end]
        if (
            not section
            or section[0] != ""
            or (index + 1 < len(SECTION_NAMES) and section[-1] != "")
        ):
            errors.append(f"{name}: separate headings and content with blank lines.")
        sections[name] = (
            section[1:-1] if index + 1 < len(SECTION_NAMES) else section[1:]
        )
    patterns: dict[str, list[str]] = {
        "Outcome": [r"\S.+"],
        "Inputs": [
            rf"- {label}: \S.+" for label in ("Required", "Optional", "Default")
        ],
        "Rules": [rf"- R{number}: \S.+" for number in range(1, 4)],
        "Workflow": [rf"{number}\. \S.+" for number in range(1, 5)],
        "Decisions": [
            r"\| Condition \| Action \|",
            r"\|\s*-{3,}\s*\|\s*-{3,}\s*\|",
            *[r"\| [^|\s][^|]* \| [^|\s][^|]* \|" for _ in range(4)],
        ],
        "Output": [r"Return:", *[r"- \S.+" for _ in range(3)]],
        "Completion criteria": [r"- \S.+", r"- \S.+"],
    }
    for name, section_patterns in patterns.items():
        if not matches_lines(sections[name], section_patterns):
            errors.append(
                f"{name}: content must follow the template's line structure and item counts."
            )
    references = sections["References"]
    if not references or not all(REFERENCE.fullmatch(line) for line in references):
        errors.append(
            "References: use '- Read `references/path` when ...' or '- Run `scripts/path` to ...'."
        )
    return errors


def validate_file(path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    try:
        content = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        return [f"Cannot read UTF-8 skill: {error}"]
    errors = validate_skill(content, max_chars)
    if path.name != "SKILL.md":
        errors.append("The entrypoint filename must be SKILL.md.")
    frontmatter = FRONTMATTER.match(content)
    if frontmatter and frontmatter[1] != path.parent.name:
        errors.append("The frontmatter name must match the parent directory name.")
    resources = {match[0].rstrip(".") for match in LOCAL_RESOURCE.finditer(content)}
    resources.update(match[1] or match[2] for match in REFERENCE.finditer(content))
    for relative in sorted(resources):
        target = (path.parent / relative).resolve()
        exists = target.is_dir() if relative.endswith("/") else target.is_file()
        if not target.is_relative_to(path.parent.resolve()) or not exists:
            errors.append(
                f"Referenced resource must exist inside the skill: {relative}"
            )
    return errors


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the supplied strict skill template."
    )
    parser.add_argument("skill", type=Path)
    parser.add_argument("--max-chars", type=positive_integer, default=DEFAULT_MAX_CHARS)
    arguments = parser.parse_args()
    errors = validate_file(arguments.skill, arguments.max_chars)
    if errors:
        sys.stderr.write("\n".join(f"FAIL: {error}" for error in errors) + "\n")
        return 1
    count = len(arguments.skill.read_bytes().decode("utf-8"))
    sys.stdout.write(
        f"PASS: {arguments.skill} ({count}/{arguments.max_chars} characters)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
