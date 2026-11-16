from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_failure_models import OAuthFailureReason, OAuthFailureStage
from umbod.core.connectors.downstream_mcp.personal_oauth_configuration import PersonalOAuthPolicy
from .models import PersonalOAuthSetupDiscovery, PersonalOAuthSetupScopeMismatch, SetupModel, ValidatedPersonalOAuthSetup


class PersonalOAuthSetupQuery(SetupModel):
    connector_id: str = Field(min_length=1)
    redirect_uri: str = Field(min_length=1, max_length=4096)


class StartPersonalOAuthSetup(PersonalOAuthSetupQuery):
    expected_revision: str = Field(min_length=1, max_length=128)
    operation: Literal["discovery", "validation"]


class PersonalOAuthSetupBinding(PersonalOAuthSetupQuery):
    definition_fingerprint: str
    policy_revision: str


class SetupRequired(SetupModel):
    status: Literal["required"] = "required"


class SetupInProgress(SetupModel):
    status: Literal["in_progress"] = "in_progress"
    operation: Literal["discovery", "validation"]
    attempt_id: str
    lease_expires_at: datetime


class SetupCompleted(SetupModel):
    checked_at: datetime


class SetupDiscovered(SetupCompleted):
    status: Literal["discovered"] = "discovered"
    discovery: PersonalOAuthSetupDiscovery


class SetupValidated(SetupCompleted):
    status: Literal["validated"] = "validated"
    result: ValidatedPersonalOAuthSetup


class SetupScopeMismatch(SetupCompleted):
    status: Literal["scope_mismatch"] = "scope_mismatch"
    result: PersonalOAuthSetupScopeMismatch


class SetupFailed(SetupCompleted):
    status: Literal["failed"] = "failed"
    stage: OAuthFailureStage
    reason: OAuthFailureReason | Literal["unsupported"]


SetupState = Annotated[SetupRequired | SetupInProgress | SetupDiscovered | SetupValidated | SetupScopeMismatch | SetupFailed, Field(discriminator="status")]
SetupCompletion = SetupDiscovered | SetupValidated | SetupScopeMismatch | SetupFailed


class PersonalOAuthSetupStatus(SetupModel):
    connector_id: str
    revision: str
    policy_revision: str
    redirect_uri: str
    state: SetupState


class PersonalOAuthSetupReceipt(SetupModel):
    binding: PersonalOAuthSetupBinding
    revision: str
    state: SetupState


class StartedPersonalOAuthSetup(SetupModel):
    receipt: PersonalOAuthSetupReceipt
    endpoint_url: str
    policy: PersonalOAuthPolicy


class CompletePersonalOAuthSetup(SetupModel):
    started: StartedPersonalOAuthSetup
    state: SetupCompletion


class PersonalOAuthSetupConflict(ValueError):
    pass


class PersonalOAuthSetupRequired(ValueError):
    pass
