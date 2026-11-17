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


def test_workflow_preserves_exact_four_reporting_instructions() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    workflow = content.split("## Workflow\n\n", 1)[1].split("\n\n## Decisions", 1)[0]
    assert workflow.splitlines() == [
        f"{number}. {instruction}"
        for number, instruction in enumerate(
            [
                "Discover Umbod's agent-behaviour playbooks at `umbod://agent-behaviour/playbooks` and read the selected playbook's current instructions before self-reporting obstacles.",
                "Call `report_diagnostic` with `trigger=proactive` only when the playbook allows proactive reporting and the user and client authorize it, otherwise do not submit a report.",
                "Follow the current reporting schema and privacy guidance, assess every selected pattern exactly once, and include only short factual summaries without transcripts, secrets, credentials, or hidden reasoning.",
                "Generate one UUID idempotency key before submission, retry uncertain outcomes only with the identical payload and key, and claim success only after receiving a durable receipt.",
            ],
            start=1,
        )
    ]
