from typing import TypedDict, Unpack

from umbod.core.invocation.diagnostics import InvocationFailureDiagnostic, PERSONAL_RUNTIME_FAILURE

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator

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

    @field_validator("result")
    @classmethod
    def validate_result_metadata(cls, result: dict[str, object]) -> dict[str, object]:
        if "_meta" in result and not isinstance(result["_meta"], dict):
            raise ValueError("Result metadata must be a JSON object")
        return result


class PersonalRuntimeFailureOptions(TypedDict, total=False):
    diagnostic: InvocationFailureDiagnostic


class PersonalRuntimeUnavailable(ValueError):
    def __init__(self, message: str, **options: Unpack[PersonalRuntimeFailureOptions]) -> None:
        unknown_options = options.keys() - PersonalRuntimeFailureOptions.__annotations__.keys()
        if unknown_options:
            raise TypeError(f"Unexpected failure options: {sorted(unknown_options)}")
        super().__init__(message)
        self.diagnostic = options.get("diagnostic", PERSONAL_RUNTIME_FAILURE)


class PersonalAuthorizationRejected(PersonalRuntimeUnavailable):
    pass
