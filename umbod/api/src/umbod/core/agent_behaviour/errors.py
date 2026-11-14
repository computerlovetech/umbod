from typing import Literal

from pydantic import Field

from .models import BehaviourConfiguration, BehaviourModel


class AgentBehaviourError(Exception):
    code = "agent_behaviour_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class RevisionConflict(AgentBehaviourError):
    code = "revision_conflict"

    def __init__(self, current: BehaviourConfiguration) -> None:
        super().__init__()
        self.current = current


class ConfigurationIssue(BehaviourModel):
    path: str = Field(max_length=200)
    code: Literal["duplicate_id", "unknown_pattern", "disabled_pattern"]


class ConfigurationInvalid(AgentBehaviourError):
    code = "configuration_invalid"

    def __init__(self, issues: tuple[ConfigurationIssue, ...]) -> None:
        super().__init__()
        self.issues = issues


class InstructionsUnavailable(AgentBehaviourError):
    code = "instructions_unavailable"


class CallerNotAuthorized(AgentBehaviourError):
    code = "unauthorized"


class ReportInvalid(AgentBehaviourError):
    code = "report_invalid"


class StaleConfiguration(ReportInvalid):
    code = "stale_configuration"


class ProactiveDisabled(ReportInvalid):
    code = "proactive_disabled"


class IdempotencyConflict(AgentBehaviourError):
    code = "idempotency_conflict"


class ReportGone(AgentBehaviourError):
    code = "report_gone"


class ReportNotFound(AgentBehaviourError):
    code = "report_not_found"


class StorageUnavailable(AgentBehaviourError):
    code = "storage_unavailable"
