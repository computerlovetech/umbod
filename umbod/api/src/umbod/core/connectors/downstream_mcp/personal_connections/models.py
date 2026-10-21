from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class CanonicalPrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    namespace: str = Field(min_length=1, pattern=r"\S")
    subject: str = Field(min_length=1, pattern=r"\S")


class PersonalConnectionKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    principal: CanonicalPrincipal
    connector_id: str = Field(min_length=1)


class Unauthorized(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["unauthorized"] = "unauthorized"


class Authorized(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["authorized"] = "authorized"
    authorization: SecretStr = Field(min_length=1)


Authorization = Annotated[Authorized | Unauthorized, Field(discriminator="kind")]


class MissingPersonalConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PersonalConnectionKey
    enabled: Literal[False] = False
    authorization: Unauthorized = Unauthorized()


class PersonalConnection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PersonalConnectionKey
    enabled: bool
    authorization: Authorization
    revision: str = Field(min_length=1)


PersonalConnectionState = PersonalConnection | MissingPersonalConnection


class SetPersonalConnectionEnabled(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PersonalConnectionKey
    enabled: bool


class ReplacePersonalAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: PersonalConnectionKey
    expected_revision: str = Field(min_length=1)
    authorization: Authorized


def set_enabled(
    state: PersonalConnectionState, enabled: bool
) -> PersonalConnectionState:
    if state.enabled == enabled:
        return state
    return PersonalConnection(
        key=state.key,
        enabled=enabled,
        authorization=state.authorization,
        revision=uuid4().hex,
    )


def disconnected(state: PersonalConnectionState) -> PersonalConnectionState:
    if isinstance(state, MissingPersonalConnection):
        return state
    return PersonalConnection(
        key=state.key, enabled=False, authorization=Unauthorized(), revision=uuid4().hex
    )


def replace_authorization(
    state: PersonalConnectionState, command: ReplacePersonalAuthorization
) -> PersonalConnection:
    if (
        not isinstance(state, PersonalConnection)
        or state.revision != command.expected_revision
    ):
        raise StalePersonalConnectionRevision()
    if state.authorization == command.authorization:
        return state
    return PersonalConnection(
        key=state.key,
        enabled=state.enabled,
        authorization=command.authorization,
        revision=uuid4().hex,
    )


class StalePersonalConnectionRevision(ValueError):
    pass


class MissingCanonicalPrincipal(PermissionError):
    pass
