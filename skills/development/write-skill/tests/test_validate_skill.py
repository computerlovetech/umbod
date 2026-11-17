import importlib.util
import json
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

    def test_default_budget_accepts_3000_characters_and_rejects_3001(self) -> None:
        for count in (3000, 3001):
            content = self.content.replace(
                "A focused skill", "A focused skill" + "x" * (count - len(self.content))
            )
            with self.subTest(count=count):
                errors = VALIDATOR.validate_skill(content)
                self.assertEqual(
                    errors,
                    []
                    if count == 3000
                    else ["Character count 3001 exceeds limit 3000."],
                )

    def test_character_budget_counts_unicode_characters_not_bytes(self) -> None:
        content = self.content.replace("A focused skill", "A focused café skill")
        self.assertEqual(VALIDATOR.validate_skill(content, len(content)), [])

    def test_nonpositive_budget_is_rejected(self) -> None:
        errors = VALIDATOR.validate_skill(self.content, 0)
        self.assertIn("Character budget must be positive.", errors)
        self.assertIn(
            "Cannot assess character count against a nonpositive budget.", errors
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

    def test_manual_invocation_safeguard_is_compatible(self) -> None:
        content = self.content.replace(
            "\n---\n\n# Write skill",
            "\ndisable-model-invocation: true\n---\n\n# Write skill",
        )
        self.assertEqual(VALIDATOR.validate_skill(content, len(content)), [])

    def test_invalid_or_duplicate_manual_invocation_metadata_is_rejected(self) -> None:
        for metadata in (
            "disable-model-invocation: yes",
            'disable-model-invocation: "true"',
            "disable-model-invocation: true\ndisable-model-invocation: true",
            "disable-model-invocation: true\nextra: value",
        ):
            content = self.content.replace(
                "\n---\n\n# Write skill", f"\n{metadata}\n---\n\n# Write skill"
            )
            with self.subTest(metadata=metadata):
                results = {
                    result.name: result
                    for result in VALIDATOR.report_skill(content, len(content))
                }
                self.assertFalse(results["frontmatter format"].passed)
                self.assertTrue(results["description trigger"].passed)
                self.assertTrue(results["heading order"].passed)

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

    def test_self_contained_skill_can_declare_no_references(self) -> None:
        content = self.content[: self.content.index("## References")] + (
            "## References\n\n- None required.\n"
        )
        self.assertEqual(VALIDATOR.validate_skill(content), [])

    def test_no_references_marker_cannot_be_mixed_with_resource_lines(self) -> None:
        content = self.content.replace(
            "## References\n\n", "## References\n\n- None required.\n"
        )
        results = {result.name: result for result in VALIDATOR.report_skill(content)}
        self.assertFalse(results["References structure"].passed)

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

    def test_independent_failures_survive_invalid_frontmatter_and_headings(
        self,
    ) -> None:
        content = self.content.replace("description: >", "description: >-")
        content = content.replace("## Inputs", "## Missing")
        content = content.replace("- R3:", "- R4:")
        content = content.replace("4. Run", "5. Run").rstrip("\n")
        results = {result.name: result for result in VALIDATOR.report_skill(content, 1)}
        for name in (
            "character count",
            "final newline",
            "frontmatter format",
            "heading order",
            "Inputs spacing",
            "Inputs structure",
            "Rules structure",
            "Workflow structure",
        ):
            with self.subTest(name=name):
                self.assertFalse(results[name].passed)
                self.assertTrue(results[name].details)
                self.assertTrue(results[name].guidance)
        self.assertTrue(results["Outcome structure"].passed)
        self.assertTrue(results["Rules spacing"].passed)

    def test_description_trigger_is_independent_of_frontmatter_format(self) -> None:
        for description in (
            'description: "Author skills. Use when creating skills."',
            "description: Author skills. Use when creating skills.",
            "description: |-\n  Author skills. Use when creating skills.",
        ):
            content = self.content.replace(
                self.content[
                    self.content.index("description:") : self.content.index("\n---", 4)
                ],
                description,
            )
            with self.subTest(description=description):
                results = {
                    result.name: result for result in VALIDATOR.report_skill(content)
                }
                self.assertFalse(results["frontmatter format"].passed)
                self.assertTrue(results["description trigger"].passed)

    def test_reordered_sections_are_still_checked_individually(self) -> None:
        content = self.content.replace("## Inputs", "## Temporary")
        content = content.replace("## Rules", "## Inputs").replace(
            "## Temporary", "## Rules"
        )
        results = {result.name: result for result in VALIDATOR.report_skill(content)}
        self.assertFalse(results["heading order"].passed)
        self.assertFalse(results["Rules structure"].passed)
        self.assertFalse(results["Inputs structure"].passed)
        self.assertTrue(results["Workflow structure"].passed)

    def test_file_reports_always_include_all_checks(self) -> None:
        expected = {
            "positive budget",
            "character count",
            "LF line endings",
            "final newline",
            "placeholders",
            "frontmatter format",
            "description trigger",
            "title",
            "heading order",
            "title spacing",
            "filename",
            "directory/name",
            "resources",
            "UTF-8/readability",
        } | {
            f"{name} {kind}"
            for name in VALIDATOR.SECTION_NAMES
            for kind in ("spacing", "structure")
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            for content in (None, b"\xff", b"", self.content.encode("utf-8")):
                with self.subTest(content=content):
                    if content is not None:
                        path.write_bytes(content)
                    results = VALIDATOR.report_file(path)
                    self.assertEqual({result.name for result in results}, expected)
                    self.assertEqual(len(results), len(expected))
                    if content is None or content == b"\xff":
                        for result in results:
                            if result.name not in ("positive budget", "filename"):
                                self.assertFalse(result.passed, result.name)

    def test_line_endings_and_final_newline_are_independent(self) -> None:
        results = {
            result.name: result
            for result in VALIDATOR.report_skill(self.content.replace("\n", "\r\n"))
        }
        self.assertFalse(results["LF line endings"].passed)
        self.assertTrue(results["final newline"].passed)
        self.assertTrue(results["Outcome structure"].passed)

    def test_spacing_does_not_hide_valid_section_structure(self) -> None:
        content = self.content.replace("## Rules\n\n", "## Rules\n")
        results = {result.name: result for result in VALIDATOR.report_skill(content)}
        self.assertFalse(results["Rules spacing"].passed)
        self.assertTrue(results["Rules structure"].passed)

    def test_missing_frontmatter_does_not_hide_body_failures(self) -> None:
        body = self.content[self.content.index("# Write skill") :].replace(
            "Return:", "Deliver:"
        )
        results = {result.name: result for result in VALIDATOR.report_skill(body)}
        self.assertFalse(results["frontmatter format"].passed)
        self.assertFalse(results["description trigger"].passed)
        self.assertFalse(results["Output structure"].passed)
        self.assertTrue(results["heading order"].passed)

    def test_check_results_are_immutable(self) -> None:
        result = VALIDATOR.report_skill(self.content)[0]
        self.assertIsInstance(result.details, tuple)
        with self.assertRaises(AttributeError):
            result.passed = False

    def test_cli_directory_scan_excludes_supporting_templates(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(SKILL_DIRECTORY), "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["passed"])
        self.assertEqual(
            [entry["path"] for entry in report["reports"]],
            [str(SKILL_DIRECTORY / "SKILL.md")],
        )
        self.assertTrue(
            all(check["passed"] for check in report["reports"][0]["checks"])
        )

    def test_recursive_discovery_excludes_all_support_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "one/SKILL.md",
                "nested/two/SKILL.md",
                "references/templates/SKILL.md",
                "scripts/nested/SKILL.md",
                "tests/SKILL.md",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("invalid", encoding="utf-8")
            self.assertEqual(
                VALIDATOR.discover_skills(root),
                (root / "nested/two/SKILL.md", root / "one/SKILL.md"),
            )

    def test_cli_reports_specific_guidance_and_all_checks(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(SKILL_DIRECTORY / "SKILL.md"),
                "--max-chars",
                "1",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("FAIL: character count", result.stdout)
        self.assertIn("PASS: Outcome structure", result.stdout)
        self.assertIn("Guidance: Move detail to supporting files", result.stdout)

    def test_cli_invalid_utf8_json_reports_unavailable_checks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            path.write_bytes(b"\xff")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(path), "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        checks = {check["name"]: check for check in report["reports"][0]["checks"]}
        self.assertFalse(report["passed"])
        self.assertIn("Cannot read UTF-8", checks["UTF-8/readability"]["details"][0])
        self.assertFalse(checks["resources"]["passed"])
        self.assertTrue(checks["resources"]["guidance"])

    def test_extra_section_boundary_blank_lines_fail_spacing_only(self) -> None:
        content = self.content.replace("## Rules\n\n", "## Rules\n\n\n")
        results = {result.name: result for result in VALIDATOR.report_skill(content)}
        self.assertFalse(results["Rules spacing"].passed)
        self.assertTrue(results["Rules structure"].passed)

    def test_empty_directory_is_a_reported_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(SCRIPT), directory, "--format", "json"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)["passed"])
        self.assertIn("No SKILL.md", json.loads(result.stdout)["errors"][0])

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
