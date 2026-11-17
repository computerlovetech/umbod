import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_readme_navigation.py"


class ReadmeNavigationChecks(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.repository = Path(temporary_directory.name).resolve()
        self.write_file("AGENTS.md", "[Source](app/src/README.md)\n")
        self.write_file("app/src/README.md", "# Source\n")

    def write_file(self, relative_path: str, content: str) -> Path:
        path = self.repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def check_navigation(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), str(self.repository), *arguments],
            capture_output=True, text=True, check=False, timeout=10,
        )

    def test_explicit_child_and_sibling_links_make_modules_reachable(self) -> None:
        self.write_file("app/src/README.md", "[Feature](feature/README.md)\n")
        self.write_file("app/src/feature/README.md", "[Sibling](../other/README.md)\n")
        self.write_file("app/src/other/README.md", "[Cycle](../README.md)\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unlinked_child_readme_fails_with_its_path(self) -> None:
        self.write_file("app/src/feature/README.md", "# Feature\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unreachable source README: app/src/feature/README.md", result.stderr)

    def test_directory_link_does_not_hide_missing_connector_bridge(self) -> None:
        self.write_file("app/src/README.md", "[Connectors](connectors/)\n")
        self.write_file("app/src/connectors/mcp/README.md", "# MCP\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("directory navigation hides README links: connectors/", result.stderr)
        self.assertIn("unreachable source README: app/src/connectors/mcp/README.md", result.stderr)

    def test_directory_link_to_existing_readme_requires_explicit_file_link(self) -> None:
        self.write_file("app/src/README.md", "[Feature](feature/)\n")
        self.write_file("app/src/feature/README.md", "# Feature\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("directory navigation hides README links: feature/", result.stderr)

    def test_direct_links_to_grandchildren_do_not_require_intermediate_readmes(self) -> None:
        self.write_file("app/src/README.md", "[MCP](connectors/mcp/README.md)\n")
        self.write_file("app/src/connectors/mcp/README.md", "# MCP\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_contributor_directory_links_fail_even_when_agent_navigation_is_complete(self) -> None:
        self.write_file("app/README.md", "[Source](src/)\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("app/README.md: directory navigation hides README links: src/", result.stderr)
        self.assertNotIn("unreachable source README:", result.stderr)

    def test_directory_without_module_documentation_is_allowed(self) -> None:
        self.write_file("app/src/README.md", "[Implementation](feature/)\n")
        self.write_file("app/src/feature/service.py", "")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_disconnected_cycle_is_not_reachable(self) -> None:
        self.write_file("app/src/first/README.md", "[Second](../second/README.md)\n")
        self.write_file("app/src/second/README.md", "[First](../first/README.md)\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.count("unreachable source README:"), 2)

    def test_excluded_generated_and_installed_readmes_are_ignored(self) -> None:
        for directory in ("node_modules", ".agents", "dist", "__pycache__"):
            self.write_file(f"app/src/{directory}/module/README.md", "# Generated\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_root_relative_encoded_reference_and_fragment_links_are_navigation(self) -> None:
        self.write_file("app/src/README.md", "[Feature][feature]\n\n[feature]: /app/src/my%20feature/README.md#files\n")
        self.write_file("app/src/my feature/README.md", "# Files\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_readme_images_and_external_links_do_not_make_modules_reachable(self) -> None:
        self.write_file("app/src/README.md", "![Feature](feature/README.md)\n[External](https://example.org/app/src/feature/README.md)\n")
        self.write_file("app/src/feature/README.md", "# Feature\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unreachable source README: app/src/feature/README.md", result.stderr)

    def test_html_anchor_is_navigation_but_html_image_is_not(self) -> None:
        self.write_file("app/src/README.md", '<a href="feature/README.md">Feature</a>\n<img src="other/README.md">\n')
        self.write_file("app/src/feature/README.md", "# Feature\n")
        self.write_file("app/src/other/README.md", "# Other\n")
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("unreachable source README: app/src/other/README.md", result.stderr)
        self.assertNotIn("unreachable source README: app/src/feature/README.md", result.stderr)

    def test_explicit_entrypoint_can_bridge_through_contributor_readme(self) -> None:
        self.write_file("README.md", "[Application](app/README.md)\n")
        self.write_file("app/README.md", "[Source](src/README.md)\n")
        result = self.check_navigation("--entrypoint", "README.md")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multiple_explicit_entrypoints_are_supported(self) -> None:
        self.write_file("other/src/README.md", "# Other\n")
        result = self.check_navigation("--entrypoint", "AGENTS.md", "--entrypoint", "other/src/README.md")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_entrypoint_fails_instead_of_reporting_success(self) -> None:
        result = self.check_navigation("--entrypoint", "missing.md")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing navigation entrypoint: missing.md", result.stderr)

    def test_repository_without_source_readmes_fails(self) -> None:
        (self.repository / "app/src/README.md").unlink()
        result = self.check_navigation()
        self.assertEqual(result.returncode, 1)
        self.assertIn("No README.md files found beneath src directories", result.stderr)


if __name__ == "__main__":
    unittest.main()
