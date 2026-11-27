from pathlib import Path

SKILL_PATH = (
    Path(__file__).resolve().parents[3]
    / "skills/integrations/umbod-agent-behaviour/SKILL.md"
)


def test_metadata_names_capability_and_difficulty_trigger() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    delimiter, frontmatter, _ = content.split("---", 2)
    assert delimiter == ""
    metadata_lines = frontmatter.strip().splitlines()
    assert metadata_lines[:2] == ["name: umbod-agent-behaviour", "description: >"]
    description = " ".join(line.strip() for line in metadata_lines[2:])
    capability, trigger = description.split(". Use when ", 1)
    assert capability
    assert trigger == "encountering difficulties."


def test_canonical_agent_behaviour_skill_has_no_local_guide_dependency() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    assert content.split("## References\n\n", 1)[1] == "- None required.\n"
    assert "references/" not in content
