from typing import cast

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec


class PersonalToolPolicyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    document: str


class PersonalToolPolicyKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str


PERSONAL_TOOL_POLICY_IDENTITY = TableIdentity("downstream_mcp_personal_tool_policies")
PERSONAL_TOOL_POLICY_CONNECTOR_ID = Field[PersonalToolPolicyRecord, str](
    PERSONAL_TOOL_POLICY_IDENTITY, "connector_id", TextCodec()
)
PERSONAL_TOOL_POLICY_DOCUMENT = Field[PersonalToolPolicyRecord, str](
    PERSONAL_TOOL_POLICY_IDENTITY, "document", TextCodec()
)
PERSONAL_TOOL_POLICY_TABLE = Table(
    PERSONAL_TOOL_POLICY_IDENTITY,
    RowCodec(PersonalToolPolicyRecord, cast(tuple[Field[PersonalToolPolicyRecord, object], ...], (
        PERSONAL_TOOL_POLICY_CONNECTOR_ID, PERSONAL_TOOL_POLICY_DOCUMENT,
    ))),
    KeyCodec(PersonalToolPolicyKey, cast(tuple[Field[PersonalToolPolicyRecord, object], ...], (
        PERSONAL_TOOL_POLICY_CONNECTOR_ID,
    ))),
)


class PersonalToolObservationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace: str
    subject: str
    connector_id: str
    document: str


class PersonalToolObservationRecordKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace: str
    subject: str
    connector_id: str


PERSONAL_TOOL_OBSERVATION_IDENTITY = TableIdentity("downstream_mcp_personal_tool_observations")
PERSONAL_TOOL_OBSERVATION_NAMESPACE = Field[PersonalToolObservationRecord, str](
    PERSONAL_TOOL_OBSERVATION_IDENTITY, "namespace", TextCodec()
)
PERSONAL_TOOL_OBSERVATION_SUBJECT = Field[PersonalToolObservationRecord, str](
    PERSONAL_TOOL_OBSERVATION_IDENTITY, "subject", TextCodec()
)
PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID = Field[PersonalToolObservationRecord, str](
    PERSONAL_TOOL_OBSERVATION_IDENTITY, "connector_id", TextCodec()
)
PERSONAL_TOOL_OBSERVATION_DOCUMENT = Field[PersonalToolObservationRecord, str](
    PERSONAL_TOOL_OBSERVATION_IDENTITY, "document", TextCodec()
)
_PERSONAL_TOOL_OBSERVATION_KEY_FIELDS = cast(
    tuple[Field[PersonalToolObservationRecord, object], ...],
    (PERSONAL_TOOL_OBSERVATION_NAMESPACE, PERSONAL_TOOL_OBSERVATION_SUBJECT, PERSONAL_TOOL_OBSERVATION_CONNECTOR_ID),
)
PERSONAL_TOOL_OBSERVATION_TABLE = Table(
    PERSONAL_TOOL_OBSERVATION_IDENTITY,
    RowCodec(
        PersonalToolObservationRecord,
        (*_PERSONAL_TOOL_OBSERVATION_KEY_FIELDS, PERSONAL_TOOL_OBSERVATION_DOCUMENT),
    ),
    KeyCodec(PersonalToolObservationRecordKey, _PERSONAL_TOOL_OBSERVATION_KEY_FIELDS),
)

