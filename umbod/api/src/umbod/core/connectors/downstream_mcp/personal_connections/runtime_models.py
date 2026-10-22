from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, PERSONAL_RUNTIME_FAILURE

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr

from umbod.core.connectors.downstream_mcp.models import DiscoveredTool, ValidatedJsonObject

from .models import PersonalConnectionKey


class PersonalRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PersonalRuntimeAuthorizationQuery(PersonalRuntimeModel):
    key: PersonalConnectionKey
    group_ids: tuple[str, ...]
    now: AwareDatetime


class PersonalRuntimeTarget(PersonalRuntimeModel):
    key: PersonalConnectionKey
    authorization_revision: str = Field(min_length=1)
    configuration_revision: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=1)
    access_token: SecretStr = Field(min_length=1)
    expires_at: AwareDatetime


class PersonalRuntimeLimits(PersonalRuntimeModel):
    operation_timeout_seconds: float = Field(gt=0, le=120)
    maximum_response_bytes: int = Field(gt=0, le=16777216)
    maximum_total_bytes: int = Field(gt=0, le=67108864)
    maximum_request_bytes: int = Field(gt=0, le=16777216)
    maximum_tool_pages: int = Field(gt=0, le=64)


class PersonalToolInventory(PersonalRuntimeModel):
    tools: tuple[DiscoveredTool, ...] = Field(max_length=256)


class PersonalToolCall(PersonalRuntimeModel):
    target: PersonalRuntimeTarget
    tool_name: str = Field(min_length=1, max_length=128)
    expected_fingerprint: str = Field(pattern="^[0-9a-f]{64}$")
    arguments: ValidatedJsonObject


class PersonalToolResult(PersonalRuntimeModel):
    result: ValidatedJsonObject


class PersonalRuntimeUnavailable(ValueError):
    def __init__(self, message: str, *, diagnostic: InvocationFailureDiagnostic = PERSONAL_RUNTIME_FAILURE) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic


class PersonalAuthorizationRejected(PersonalRuntimeUnavailable):
    pass
