import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_readme_links.py"


class SourceReadmeLinkChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.workspace: Path = Path(temporary_directory.name).resolve()
        self.repository: Path = self.workspace / "repository"
        self.repository.mkdir()

    def write_file(self, relative_path: str, content: str) -> Path:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def check_links(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), str(self.repository)],
            capture_output=True, text=True, check=False, timeout=10,
        )

    def test_source_readmes_can_link_across_their_entire_source_tree(self) -> None:
        for source in ("umbod/api/src", "umbod/frontend/src", "packages/sdk/src", "website/src"):
            with self.subTest(source=source):
                self.write_file(f"{source}/README.md", "[Module](module/README.md)\n")
                self.write_file(f"{source}/module/README.md", "[Sibling](../other/item.py)\n[Parent](../README.md)\n[Child](child/item.py)\n")
                self.write_file(f"{source}/other/item.py", "value = 1\n")
                self.write_file(f"{source}/module/child/item.py", "value = 1\n")
                result = self.check_links()
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_readmes_reject_docs_tests_and_other_package_source_trees(self) -> None:
        self.write_file("umbod/api/src/module/README.md", "# Module\n")
        for destination, target in (
            ("../../../docs/operations/guide.md", "umbod/docs/operations/guide.md"),
            ("../../tests/test_module.py", "umbod/api/tests/test_module.py"),
            ("../../../frontend/src/item.ts", "umbod/frontend/src/item.ts"),
            ("/umbod/frontend/src/item.ts", "umbod/frontend/src/item.ts"),
            ("../../src-sibling/item.py", "umbod/api/src-sibling/item.py"),
            ("../%2e%2e/tests/test_module.py", "umbod/api/tests/test_module.py"),
        ):
            with self.subTest(destination=destination):
                self.write_file(target, "Content\n")
                self.write_file("umbod/api/src/module/README.md", f"[Target]({destination})\n")
                result = self.check_links()
                self.assertEqual(result.returncode, 1)
                self.assertIn("outside source tree umbod/api/src", result.stderr)
                self.assertNotIn("missing local target", result.stderr)

    def test_frontend_readmes_cannot_link_to_backend_sources(self) -> None:
        self.write_file("umbod/api/src/item.py", "value = 1\n")
        self.write_file("umbod/frontend/src/README.md", "[Backend](/umbod/api/src/item.py)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside source tree umbod/frontend/src", result.stderr)

    def test_adrs_are_allowed_from_backend_and_frontend_sources(self) -> None:
        self.write_file("umbod/project/architecture-records/ADR-001.md", "# Decision\n")
        for source in ("umbod/api/src", "umbod/frontend/src"):
            with self.subTest(source=source):
                self.write_file(f"{source}/README.md", "[ADR](../../project/architecture-records/ADR-001.md#decision)\n")
                result = self.check_links()
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_adr_exception_does_not_include_neighboring_directories(self) -> None:
        self.write_file("umbod/project/architecture-records-old/ADR-001.md", "# Old\n")
        self.write_file("umbod/api/src/README.md", "[Old ADR](../../project/architecture-records-old/ADR-001.md)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside source tree umbod/api/src", result.stderr)

    def test_non_source_readmes_keep_existence_only_checking(self) -> None:
        self.write_file("guide.md", "# Guide\n")
        self.write_file("umbod/docs/operations/guide.md", "# Guide\n")
        self.write_file("umbod/api/tests/README.md", "[Root](../../../guide.md)\n[Docs](../../docs/operations/guide.md)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_links_are_reported_even_when_they_also_violate_source_scope(self) -> None:
        self.write_file("umbod/api/src/README.md", "[Inside](missing.md)\n[Outside](../missing.md)\n[ADR](../../project/architecture-records/missing.md)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("missing local target"), 3)
        self.assertEqual(result.stderr.count("outside source tree"), 1)
        self.assertEqual(len(result.stderr.splitlines()), 3)

    def test_source_symlinks_cannot_escape_the_source_tree(self) -> None:
        outside = self.write_file("umbod/docs/operations/guide.md", "# Guide\n")
        self.write_file("umbod/api/src/README.md", "[Guide](guide.md)\n")
        (self.repository / "umbod/api/src/guide.md").symlink_to(outside)
        result = self.check_links()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside source tree umbod/api/src", result.stderr)

    def test_adr_symlinks_cannot_extend_the_exception(self) -> None:
        outside = self.write_file("umbod/docs/operations/guide.md", "# Guide\n")
        self.write_file("umbod/api/src/README.md", "[ADR](../../project/architecture-records/ADR-001.md)\n")
        adr = self.repository / "umbod/project/architecture-records/ADR-001.md"
        adr.parent.mkdir(parents=True)
        adr.symlink_to(outside)
        result = self.check_links()
        self.assertEqual(result.returncode, 1)
        self.assertIn("outside source tree umbod/api/src", result.stderr)

    def test_images_html_and_reference_links_follow_the_source_boundary(self) -> None:
        self.write_file("umbod/docs/operations/guide.md", "# Guide\n")
        for content in (
            "![Image](/umbod/docs/operations/guide.md)",
            '<a href="/umbod/docs/operations/guide.md">Guide</a>',
            '<img src="/umbod/docs/operations/guide.md">',
            "[Guide][target]\n\n[target]: /umbod/docs/operations/guide.md",
        ):
            with self.subTest(content=content):
                self.write_file("umbod/api/src/README.md", content)
                result = self.check_links()
                self.assertEqual(result.returncode, 1)
                self.assertIn("outside source tree umbod/api/src", result.stderr)

    def test_external_links_and_anchors_are_unchanged(self) -> None:
        self.write_file("umbod/api/src/README.md", "[Web](https://example.com/docs)\n[Anchor](#module)\n[Host](//example.com/docs)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_nested_src_folders_do_not_shrink_the_package_boundary(self) -> None:
        self.write_file("umbod/api/src/other/item.py", "value = 1\n")
        self.write_file("umbod/api/src/module/src/README.md", "[Other](../../other/item.py)\n")
        result = self.check_links()
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
