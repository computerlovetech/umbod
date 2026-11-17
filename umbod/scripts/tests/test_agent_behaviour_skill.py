from pathlib import Path


SKILL_PATH = Path(__file__).resolve().parents[3] / "skills/integrations/umbod-agent-behaviour/SKILL.md"


def test_canonical_agent_behaviour_skill_has_exact_metadata_and_four_instructions() -> None:
    content = SKILL_PATH.read_text(encoding="utf-8")
    delimiter, frontmatter, body = content.split("---", 2)
    assert delimiter == ""
    assert frontmatter.strip().splitlines() == [
        "name: umbod-agent-behaviour",
        "description: Use whenever encountering difficulties.",
    ]
    assert body.strip().splitlines() == [
        "Discover Umbod's agent-behaviour playbooks at `umbod://agent-behaviour/playbooks` and read the selected playbook's current instructions before self-reporting obstacles.",
        "Call `report_diagnostic` with `trigger=proactive` only when the playbook allows proactive reporting and the user and client authorize it, otherwise do not submit a report.",
        "Follow the current reporting schema and privacy guidance, assess every selected pattern exactly once, and include only short factual summaries without transcripts, secrets, credentials, or hidden reasoning.",
        "Generate one UUID idempotency key before submission, retry uncertain outcomes only with the identical payload and key, and claim success only after receiving a durable receipt.",
    ]
