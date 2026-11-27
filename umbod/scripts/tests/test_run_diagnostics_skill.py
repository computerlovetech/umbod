from pathlib import Path

SKILL_PATH = Path(__file__).resolve().parents[3] / "skills/integrations/run-diagnostics/SKILL.md"


def test_diagnostics_skill_advertises_user_and_agent_initiated_use() -> None:
    _, frontmatter, instructions = SKILL_PATH.read_text(encoding="utf-8").split("---", 2)
    assert "name: run-diagnostics" in frontmatter
    assert "the user requests diagnostics or a concrete obstacle warrants one" in frontmatter
    assert "`trigger=user_requested`" in instructions
    assert "`trigger=proactive`" in instructions


def test_diagnostics_skill_requires_current_playbook_and_reporting_authorization() -> None:
    instructions = SKILL_PATH.read_text(encoding="utf-8")
    assert "`umbod://agent-behaviour/playbooks`" in instructions
    assert "Read the selected live playbook before assessing or submitting." in instructions
    assert "submit only if authorized by the user and client" in instructions
    assert "| Proactive reporting is not authorized | Do not submit" in instructions
