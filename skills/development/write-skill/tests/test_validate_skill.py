import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

SKILL_DIRECTORY = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIRECTORY / "scripts" / "validate_skill.py"


def load_validator() -> ModuleType:
    specification = importlib.util.spec_from_file_location("validate_skill", SCRIPT)
    if specification is None or specification.loader is None:
        raise RuntimeError("Cannot load skill validator")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


VALIDATOR = load_validator()


class TestValidateSkill(unittest.TestCase):
    def setUp(self) -> None:
        self.content = (SKILL_DIRECTORY / "SKILL.md").read_text(encoding="utf-8")

    def test_authoring_skill_passes_its_own_check(self) -> None:
        self.assertEqual(VALIDATOR.validate_file(SKILL_DIRECTORY / "SKILL.md"), [])

    def test_template_headings_match_authoring_skill(self) -> None:
        template = (
            SKILL_DIRECTORY / "references" / "templates" / "SKILL.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            [line for line in template.splitlines() if line.startswith("## ")],
            [line for line in self.content.splitlines() if line.startswith("## ")],
        )

    def test_character_budget_accepts_exact_boundary_and_rejects_one_less(self) -> None:
        self.assertEqual(VALIDATOR.validate_skill(self.content, len(self.content)), [])
        self.assertTrue(
            any(
                "exceeds" in error
                for error in VALIDATOR.validate_skill(
                    self.content, len(self.content) - 1
                )
            )
        )

    def test_character_budget_counts_unicode_characters_not_bytes(self) -> None:
        content = self.content.replace("A focused skill", "A focused café skill")
        self.assertEqual(VALIDATOR.validate_skill(content, len(content)), [])

    def test_nonpositive_budget_is_rejected(self) -> None:
        self.assertEqual(
            VALIDATOR.validate_skill(self.content, 0),
            ["Character budget must be positive."],
        )

    def test_invalid_structure_is_rejected(self) -> None:
        mutations = (
            ("name: write-skill", "name: write_skill"),
            ("description: >", "description: >-"),
            ("name: write-skill", "name: write-skill\nname: other-skill"),
            ("---\n\n# Write skill", "extra: value\n---\n\n# Write skill"),
            (". Use when creating", ". Applicable to creating"),
            ("# Write skill", "## Write skill"),
            ("## Outcome", "## Result"),
            ("## Inputs", "## Inputs\n\n### Extra"),
            ("## Rules", "## Inputs"),
            ("- Required:", "- Needed:"),
            ("- R3:", "- R4:"),
            ("4. Run", "5. Run"),
            ("| Condition | Action |", "| When | Then |"),
            (
                "| Condition | Action |\n|---|---|",
                "| Condition | Action |\n\n|---|---|",
            ),
            ("| Recovery fails |", "| Recovery fails | extra |"),
            ("Return:", "Deliver:"),
            ("- The authored SKILL.md", "The authored SKILL.md"),
            ("- The structure check exits", "1. The structure check exits"),
            (
                "- Read `references/templates/SKILL.md` when",
                "- See `references/templates/SKILL.md` when",
            ),
            ("# Write skill", "# [Skill title]"),
            ("\n\n## Outcome", "\nIntroductory prose\n\n## Outcome"),
            ("\n\n## Inputs", "\n## Inputs"),
        )
        for original, replacement in mutations:
            with self.subTest(replacement=replacement):
                self.assertNotEqual(
                    self.content, self.content.replace(original, replacement)
                )
                self.assertTrue(
                    VALIDATOR.validate_skill(
                        self.content.replace(original, replacement)
                    )
                )

    def test_empty_input_and_bad_line_endings_are_rejected(self) -> None:
        for content in (
            "",
            self.content.rstrip("\n"),
            self.content.replace("\n", "\r\n"),
        ):
            with self.subTest(length=len(content)):
                self.assertTrue(VALIDATOR.validate_skill(content))

    def test_missing_sections_and_extra_items_are_rejected(self) -> None:
        for content in (
            self.content[: self.content.index("## References")],
            self.content.replace(
                "## Workflow", "- R4: Extra constraint.\n\n## Workflow"
            ),
            self.content.replace("## Decisions", "5. Extra step.\n\n## Decisions"),
            self.content.replace(
                "## References", "- Extra acceptance condition.\n\n## References"
            ),
        ):
            with self.subTest(length=len(content)):
                self.assertTrue(VALIDATOR.validate_skill(content))

    def test_unfilled_template_is_rejected(self) -> None:
        template = SKILL_DIRECTORY / "references" / "templates" / "SKILL.md"
        self.assertTrue(
            any(
                "placeholder" in error
                for error in VALIDATOR.validate_skill(
                    template.read_text(encoding="utf-8")
                )
            )
        )

    def test_missing_resource_and_escaping_resource_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "write-skill" / "SKILL.md"
            path.parent.mkdir()
            for reference in ("references/missing.md", "references/../../outside.md"):
                path.write_text(
                    self.content.replace("references/templates/SKILL.md", reference),
                    encoding="utf-8",
                )
                self.assertTrue(
                    any(
                        "Referenced resource" in error
                        for error in VALIDATOR.validate_file(path)
                    )
                )

    def test_missing_workflow_resource_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "write-skill" / "SKILL.md"
            path.parent.mkdir()
            path.write_text(
                self.content.replace(
                    "2. Read references/templates/SKILL.md",
                    "2. Read references/nonexistent.md",
                ),
                encoding="utf-8",
            )
            self.assertIn(
                "Referenced resource must exist inside the skill: references/nonexistent.md",
                VALIDATOR.validate_file(path),
            )

    def test_wrong_filename_and_directory_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skills.md"
            path.write_text(self.content, encoding="utf-8")
            errors = VALIDATOR.validate_file(path)
            self.assertIn("The entrypoint filename must be SKILL.md.", errors)
            self.assertIn(
                "The frontmatter name must match the parent directory name.", errors
            )

    def test_unreadable_and_non_utf8_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            self.assertTrue(VALIDATOR.validate_file(path))
            path.write_bytes(b"\xff")
            self.assertTrue(VALIDATOR.validate_file(path))

    def test_cli_reports_success_failure_and_invalid_budget(self) -> None:
        for arguments, exit_code, message in (
            ([str(SKILL_DIRECTORY / "SKILL.md")], 0, "PASS:"),
            ([str(SKILL_DIRECTORY / "SKILL.md"), "--max-chars", "1"], 1, "exceeds"),
            (
                [str(SKILL_DIRECTORY / "SKILL.md"), "--max-chars", "0"],
                2,
                "must be positive",
            ),
            ([str(SKILL_DIRECTORY / "missing.md")], 1, "Cannot read UTF-8"),
        ):
            with self.subTest(arguments=arguments):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), *arguments],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, exit_code)
                self.assertIn(message, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
