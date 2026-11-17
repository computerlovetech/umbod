import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_MAX_CHARS = 3000
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
    r"description: >\n((?:  \S[^\n]*\n)+)"
    r"(?:disable-model-invocation: true\n)?---\n\n"
)
PLACEHOLDER = re.compile(r"\[[^\]\n]+\](?!\()")
LOCAL_RESOURCE = re.compile(r"(?<![\w/])(?:references|scripts)/[\w./-]+")
REFERENCE = re.compile(
    r"- (?:Read `(references/[^`]+)` when|Run `(scripts/[^`]+)` to) .+"
)
SECTION_PATTERNS = {
    "Outcome": [r"\S.+"],
    "Inputs": [rf"- {label}: \S.+" for label in ("Required", "Optional", "Default")],
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
SUPPORT_DIRECTORIES = frozenset({"references", "scripts", "tests"})


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    details: tuple[str, ...]
    guidance: str


def check(name: str, passed: bool, detail: str, guidance: str) -> CheckResult:
    return CheckResult(name, passed, () if passed else (detail,), guidance)


def matches_lines(lines: list[str], patterns: list[str]) -> bool:
    return len(lines) == len(patterns) and all(
        re.fullmatch(pattern, line) for pattern, line in zip(patterns, lines)
    )


def split_frontmatter(content: str) -> tuple[str, str]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|$)", normalized, re.DOTALL)
    if match:
        body = normalized[match.end() :]
        return match[1], body.removeprefix("\n")
    return "", normalized


def section_report(lines: list[str], name: str) -> tuple[CheckResult, CheckResult]:
    positions = [index for index, line in enumerate(lines) if line == f"## {name}"]
    spacing_guidance = f"Put a blank line after {name} and before the next heading."
    structure_guidance = (
        "Use Read/Run resource lines, or '- None required.' when the skill is self-contained."
        if name == "References"
        else f"Restore {name}'s lines and item counts from references/templates/SKILL.md."
    )
    if len(positions) != 1:
        detail = f"{name}: cannot assess content without exactly one section heading."
        return (
            check(f"{name} spacing", False, detail, spacing_guidance),
            check(f"{name} structure", False, detail, structure_guidance),
        )
    start = positions[0] + 1
    end = next(
        (
            index
            for index in range(start, len(lines))
            if re.match(r" {0,3}#", lines[index])
        ),
        len(lines),
    )
    section = lines[start:end]
    spacing = (
        len(section) >= 2
        and section[0] == ""
        and section[1] != ""
        and (
            (end == len(lines) and section[-1] != "")
            or (
                end < len(lines)
                and len(section) >= 3
                and section[-1] == ""
                and section[-2] != ""
            )
        )
    )
    trimmed = list(section)
    while trimmed and trimmed[0] == "":
        trimmed.pop(0)
    while trimmed and trimmed[-1] == "":
        trimmed.pop()
    if name == "References":
        valid = trimmed == ["- None required."] or (
            bool(trimmed) and all(REFERENCE.fullmatch(line) for line in trimmed)
        )
        detail = "References: use Read/Run resource lines, or only '- None required.' for a self-contained skill."
    else:
        valid = matches_lines(trimmed, SECTION_PATTERNS[name])
        detail = f"{name}: content must follow the template's line structure and item counts."
    return (
        check(
            f"{name} spacing",
            spacing,
            f"{name}: separate headings and content with blank lines.",
            spacing_guidance,
        ),
        check(f"{name} structure", valid, detail, structure_guidance),
    )


def report_skill(
    content: str, max_chars: int = DEFAULT_MAX_CHARS
) -> tuple[CheckResult, ...]:
    metadata, body = split_frontmatter(content)
    lines = body.splitlines()
    description = re.search(
        r"(?m)^description: (?:[>|][+-]?\n((?:  [^\n]+\n?)+)|([^\n]+))",
        metadata,
    )
    description_text = (
        " ".join(
            line.strip() for line in (description[1] or description[2]).splitlines()
        )
        if description
        else ""
    )
    trigger = re.search(r"\S.*\. Use when \S", description_text) is not None
    title = bool(lines) and re.fullmatch(r"# [^#\s].*", lines[0]) is not None
    headings = [line for line in lines if re.match(r" {0,3}#", line)]
    expected = [lines[0] if lines else ""] + [f"## {name}" for name in SECTION_NAMES]
    results = [
        check(
            "positive budget",
            max_chars > 0,
            "Character budget must be positive.",
            "Choose --max-chars greater than zero.",
        ),
        CheckResult(
            "character count",
            max_chars > 0 and len(content) <= max_chars,
            (f"{len(content)}/{max_chars} characters",)
            if 0 < max_chars >= len(content)
            else (
                f"Character count {len(content)} exceeds limit {max_chars}."
                if max_chars > 0
                else "Cannot assess character count against a nonpositive budget.",
            ),
            "Move detail to supporting files or obtain an explicit positive budget override.",
        ),
        check(
            "LF line endings",
            "\r" not in content,
            "Use LF line endings and a final newline.",
            "Replace CRLF and CR line endings with LF.",
        ),
        check(
            "final newline",
            content.endswith("\n"),
            "Use LF line endings and a final newline.",
            "End SKILL.md with a newline.",
        ),
        check(
            "placeholders",
            PLACEHOLDER.search(content) is None,
            "Replace all bracketed template placeholders.",
            "Inspect flagged brackets and replace template placeholders; bracket detection is heuristic.",
        ),
        check(
            "frontmatter format",
            FRONTMATTER.match(content) is not None,
            "Use template name and description: > frontmatter, optionally followed by disable-model-invocation: true.",
            "Restore template delimiters, name, folded description, and blank line; preserve any manual-invocation safeguard after the description.",
        ),
        check(
            "description trigger",
            trigger,
            "Description must state a capability followed by '. Use when ' and a trigger."
            if description
            else "Cannot assess description trigger: description is unavailable in delimited frontmatter.",
            "Provide a description containing a capability followed by '. Use when ' and a concrete trigger.",
        ),
        check(
            "title",
            title,
            "Start the body with one '# Skill title' heading.",
            "Place one level-one title immediately after the frontmatter blank line.",
        ),
        check(
            "heading order",
            title and headings == expected,
            "Headings must be one title followed by: "
            + ", ".join(SECTION_NAMES)
            + "; no extra headings.",
            "Restore the title and all template section headings in order, without duplicates or extra headings.",
        ),
        check(
            "title spacing",
            title and len(lines) >= 3 and lines[1] == "" and lines[2] == "## Outcome",
            "Separate the title from Outcome with one blank line and no introductory text.",
            "Put exactly one blank line between the title and ## Outcome; remove introductory prose.",
        ),
    ]
    for name in SECTION_NAMES:
        results.extend(section_report(lines, name))
    return tuple(results)


def resource_report(path: Path, content: str) -> CheckResult:
    resources = {match[0].rstrip(".") for match in LOCAL_RESOURCE.finditer(content)}
    resources.update(match[1] or match[2] for match in REFERENCE.finditer(content))
    errors: list[str] = []
    try:
        root = path.parent.resolve()
        for relative in sorted(resources):
            target = (path.parent / relative).resolve()
            exists = target.is_dir() if relative.endswith("/") else target.is_file()
            if not target.is_relative_to(root) or not exists:
                errors.append(
                    f"Referenced resource must exist inside the skill: {relative}"
                )
    except (OSError, RuntimeError) as error:
        errors.append(f"Cannot inspect referenced resources: {error}")
    return CheckResult(
        "resources",
        not errors,
        tuple(errors),
        "Create or correct each referenced resource inside the skill directory; remove escaping paths.",
    )


def report_file(
    path: Path, max_chars: int = DEFAULT_MAX_CHARS
) -> tuple[CheckResult, ...]:
    filename = check(
        "filename",
        path.name == "SKILL.md",
        "The entrypoint filename must be SKILL.md.",
        "Rename the skill entrypoint to SKILL.md.",
    )
    try:
        content = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as error:
        unavailable = tuple(
            result
            if result.name == "positive budget"
            else CheckResult(
                result.name,
                False,
                ("Cannot assess check: readable UTF-8 content is unavailable.",),
                "Restore readable UTF-8 content, then rerun. " + result.guidance,
            )
            for result in report_skill("", max_chars)
        )
        return unavailable + (
            filename,
            check(
                "directory/name",
                False,
                "Cannot assess directory/name without readable frontmatter.",
                "Restore readable UTF-8 frontmatter and match its name to the parent directory.",
            ),
            check(
                "resources",
                False,
                "Cannot assess resources without readable content.",
                "Restore readable UTF-8 content and rerun resource validation.",
            ),
            check(
                "UTF-8/readability",
                False,
                f"Cannot read UTF-8 skill: {error}",
                "Check the file path and read permissions, and save the file as UTF-8.",
            ),
        )
    metadata, _ = split_frontmatter(content)
    name = re.search(r"(?m)^name: ([^\n]+)$", metadata)
    return report_skill(content, max_chars) + (
        filename,
        check(
            "directory/name",
            name is not None and name[1] == path.parent.name,
            "The frontmatter name must match the parent directory name."
            if name
            else "Cannot assess directory/name: frontmatter name is unavailable.",
            "Set frontmatter name to the lowercase, hyphenated parent directory name.",
        ),
        resource_report(path, content),
        check("UTF-8/readability", True, "", "Save the skill as readable UTF-8."),
    )


def failed_details(results: tuple[CheckResult, ...]) -> list[str]:
    return list(
        dict.fromkeys(
            detail
            for result in results
            if not result.passed
            for detail in result.details
        )
    )


def validate_skill(content: str, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    return failed_details(report_skill(content, max_chars))


def validate_file(path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> list[str]:
    return failed_details(report_file(path, max_chars))


def positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def discover_skills(path: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            candidate
            for candidate in path.rglob("SKILL.md")
            if not SUPPORT_DIRECTORIES.intersection(
                candidate.relative_to(path).parts[:-1]
            )
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the supplied strict skill template or skill directory tree."
    )
    parser.add_argument("skill", type=Path)
    parser.add_argument("--max-chars", type=positive_integer, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    arguments = parser.parse_args()
    try:
        paths = (
            discover_skills(arguments.skill)
            if arguments.skill.is_dir()
            else (arguments.skill,)
        )
    except OSError as error:
        parser.exit(1, f"FAIL: Cannot discover skills: {error}\n")
    reports = [(path, report_file(path, arguments.max_chars)) for path in paths]
    passed = bool(reports) and all(
        result.passed for _, results in reports for result in results
    )
    if arguments.format == "json":
        sys.stdout.write(
            json.dumps(
                {
                    "passed": passed,
                    "reports": [
                        {
                            "path": str(path),
                            "checks": [asdict(result) for result in results],
                        }
                        for path, results in reports
                    ],
                    "errors": []
                    if reports
                    else ["No SKILL.md files found outside supporting directories."],
                },
                indent=2,
            )
            + "\n"
        )
    else:
        if not reports:
            sys.stderr.write(
                "FAIL: No SKILL.md files found outside supporting directories.\nGuidance: Supply a skill file or a directory containing skills.\n"
            )
        for path, results in reports:
            sys.stdout.write(
                f"{'PASS' if all(result.passed for result in results) else 'FAIL'}: {path}\n"
            )
            for result in results:
                sys.stdout.write(
                    f"  {'PASS' if result.passed else 'FAIL'}: {result.name}\n"
                )
                for detail in result.details:
                    sys.stdout.write(f"    {detail}\n")
                if not result.passed:
                    sys.stdout.write(f"    Guidance: {result.guidance}\n")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
