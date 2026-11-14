from .models import BehaviourConfiguration, BehaviourPattern, DiagnosticPlaybook


DEFAULT_CONFIGURATION = BehaviourConfiguration(
    revision=1,
    patterns=(
        BehaviourPattern(
            id="missing-context",
            name="Missing context",
            description="The agent lacks information needed to complete the task.",
            assessment_prompt="The agent lacks information needed to complete the task.",
            inclusion_criteria="Required instructions, specifications, files or prior decisions are unavailable and materially prevent or undermine completion.",
            exclusion_criteria="An ordinary clarification resolves the question without blocking the task, or the information is available in authorized context.",
            categories=("context",),
            polarity="negative",
            enabled=True,
        ),
        BehaviourPattern(
            id="tool-problems",
            name="Tool problems",
            description="A tool fails, is unavailable, or returns unusable results.",
            assessment_prompt="A tool fails, is unavailable, or returns unusable results.",
            inclusion_criteria="An observed error, unavailable tool or unusable response prevents the intended operation or requires a workaround.",
            exclusion_criteria="The tool returns a valid empty result, correctly denies an unauthorized action, or has not been attempted.",
            categories=("tools",),
            polarity="negative",
            enabled=True,
        ),
        BehaviourPattern(
            id="task-blocked",
            name="Task blocked",
            description="The agent cannot proceed and needs help.",
            assessment_prompt="The agent cannot proceed and needs help.",
            inclusion_criteria="The next required step cannot be completed safely with the available authorized context and capabilities, and external help is needed.",
            exclusion_criteria="The task is still progressing, an available safe alternative exists, or the agent correctly refuses a prohibited request.",
            categories=("progress",),
            polarity="negative",
            enabled=True,
        ),
        BehaviourPattern(
            id="user-correction",
            name="User correction",
            description="The user corrects the agent's understanding or result.",
            assessment_prompt="The user corrects the agent's understanding or result.",
            inclusion_criteria="The user identifies an incorrect assumption, misunderstanding or error in the agent's prior work.",
            exclusion_criteria="The user changes their preference, adds a new requirement, or asks a follow-up without correcting prior work.",
            categories=("feedback",),
            polarity="neutral",
            enabled=True,
        ),
    ),
    playbooks=(
        DiagnosticPlaybook(
            id="behaviour-review",
            name="Behaviour review",
            collection_instructions="Review only the current task context and tool results you are authorized to use. Assess every selected pattern. Record a short factual summary and up to three minimal observations for each observed pattern. Use not_assessed when context is insufficient. Never collect full transcripts, credentials, personal data, or hidden reasoning. Report only when requested unless automatic reporting is explicitly allowed and the user and client permit it.",
            pattern_ids=("missing-context", "tool-problems", "task-blocked", "user-correction"),
            enabled=True,
            allow_proactive=False,
        ),
    ),
)


def get_default_configuration() -> BehaviourConfiguration:
    return DEFAULT_CONFIGURATION
