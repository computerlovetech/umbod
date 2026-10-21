from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from umbod.core.capabilities import CapabilityAvailability, CapabilityIdentity
from umbod.core.capabilities.availability import (
    UnrestrictedCapabilityActivation,
    UnrestrictedCapabilityPermissionPolicy,
    UnrestrictedCapabilityPublication,
    UnrestrictedCapabilityReadiness,
)
from umbod.core.connectors.downstream_mcp.models import (
    NoAuthConnectorDefinition,
    NoAuthCredentialState,
    OAuthConnectorDefinition,
)
from umbod.core.connectors.downstream_mcp.probe import DiscoverDownstreamTools
from umbod.core.connectors.downstream_mcp.runtime import (
    DownstreamRuntimeResolver,
    DownstreamRuntimeUnavailable,
    InMemoryDownstreamRuntimeResolver,
    SharedDownstreamRuntimeResolver,
    SharedRuntimeConnection,
)
from umbod.core.connectors.downstream_mcp.stores import (
    ConnectorDefinitionFound,
    ConnectorDefinitionMissing,
    ConnectorDefinitionStore,
    CredentialFound,
    CredentialMissing,
    EncryptedCredentialStore,
)


def identity() -> CapabilityIdentity:
    return CapabilityIdentity(
        connector_kind="downstream_mcp", connector_id="alpha",
        capability_kind="tool", capability_key="lookup",
    )


def connection() -> SharedRuntimeConnection:
    return SharedRuntimeConnection(command=DiscoverDownstreamTools(
        definition=NoAuthConnectorDefinition(
            connector_id="alpha", display_name="Alpha", endpoint_url="https://alpha.example/mcp",
        ),
        credential=NoAuthCredentialState(connector_id="alpha"),
    ))


def availability() -> CapabilityAvailability:
    return CapabilityAvailability(
        UnrestrictedCapabilityPublication(), UnrestrictedCapabilityActivation(),
        UnrestrictedCapabilityReadiness(), UnrestrictedCapabilityPermissionPolicy(),
    )


@pytest.mark.asyncio
async def test_inmemory_runtime_resolves_only_explicit_complete_identity() -> None:
    shared = connection()
    resolver: DownstreamRuntimeResolver = InMemoryDownstreamRuntimeResolver({identity(): shared})
    assert await resolver.resolve(identity()) == shared
    for changes in (
        {"connector_kind": "openapi"}, {"connector_id": "other"},
        {"capability_kind": "prompt"}, {"capability_key": "other"},
    ):
        with pytest.raises(DownstreamRuntimeUnavailable):
            await resolver.resolve(CapabilityIdentity.model_validate({**identity().model_dump(), **changes}))


@pytest.mark.asyncio
async def test_shared_runtime_rereads_definition_and_credentials_on_each_resolution() -> None:
    shared = connection()
    definitions = AsyncMock(spec=ConnectorDefinitionStore)
    credentials = AsyncMock(spec=EncryptedCredentialStore)
    definitions.get.return_value = ConnectorDefinitionFound(definition=shared.command.definition)
    credentials.get.return_value = CredentialFound(credential=shared.command.credential)
    resolver: DownstreamRuntimeResolver = SharedDownstreamRuntimeResolver(availability(), definitions, credentials)
    assert await resolver.resolve(identity()) == shared
    replacement = shared.command.definition.model_copy(update={"endpoint_url": "https://new.example/mcp"})
    definitions.get.return_value = ConnectorDefinitionFound(definition=replacement)
    assert (await resolver.resolve(identity())).command.definition == replacement
    credentials.get.return_value = CredentialMissing(connector_id="alpha")
    with pytest.raises(DownstreamRuntimeUnavailable):
        await resolver.resolve(identity())


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["missing", "personal"])
async def test_shared_runtime_rejects_missing_or_personal_definition_with_planted_credentials(state: str) -> None:
    definitions = AsyncMock(spec=ConnectorDefinitionStore)
    credentials = AsyncMock(spec=EncryptedCredentialStore)
    credentials.get.return_value = CredentialFound(credential=connection().command.credential)
    definitions.get.return_value = (
        ConnectorDefinitionMissing(connector_id="alpha") if state == "missing" else
        ConnectorDefinitionFound(definition=OAuthConnectorDefinition(
            connector_id="alpha", display_name="Alpha", endpoint_url="https://alpha.example/mcp",
            authorization_mode="personal",
        ))
    )
    resolver: DownstreamRuntimeResolver = SharedDownstreamRuntimeResolver(availability(), definitions, credentials)
    with pytest.raises(DownstreamRuntimeUnavailable):
        await resolver.resolve(identity())


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["publication", "activation", "readiness", "permission"])
async def test_shared_runtime_checks_current_full_availability(stage: str) -> None:
    publication = AsyncMock(spec=UnrestrictedCapabilityPublication)
    activation = AsyncMock(spec=UnrestrictedCapabilityActivation)
    readiness = AsyncMock(spec=UnrestrictedCapabilityReadiness)
    permissions = AsyncMock(spec=UnrestrictedCapabilityPermissionPolicy)
    publication.is_published.return_value = True
    activation.is_enabled.return_value = True
    readiness.is_ready.return_value = True
    permissions.allows.return_value = True
    checks = {"publication": publication.is_published, "activation": activation.is_enabled,
              "readiness": readiness.is_ready, "permission": permissions.allows}
    definitions = AsyncMock(spec=ConnectorDefinitionStore)
    credentials = AsyncMock(spec=EncryptedCredentialStore)
    definitions.get.return_value = ConnectorDefinitionFound(definition=connection().command.definition)
    credentials.get.return_value = CredentialFound(credential=connection().command.credential)
    resolver: DownstreamRuntimeResolver = SharedDownstreamRuntimeResolver(
        CapabilityAvailability(publication, activation, readiness, permissions), definitions, credentials,
    )
    assert await resolver.resolve(identity()) == connection()
    checks[stage].return_value = False
    with pytest.raises(DownstreamRuntimeUnavailable):
        await resolver.resolve(identity())
    assert checks[stage].call_args.args == (identity(),)


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"connector_kind": "openapi"}, {"connector_id": "other"},
    {"capability_kind": "prompt"}, {"capability_key": "other"},
])
async def test_shared_runtime_does_not_substitute_a_different_capability(changes: dict[str, str]) -> None:
    readiness = AsyncMock(spec=UnrestrictedCapabilityReadiness)

    async def exact_capability(candidate: CapabilityIdentity) -> bool:
        return candidate == identity()

    readiness.is_ready.side_effect = exact_capability
    definitions = AsyncMock(spec=ConnectorDefinitionStore)
    credentials = AsyncMock(spec=EncryptedCredentialStore)
    definitions.get.return_value = ConnectorDefinitionFound(definition=connection().command.definition)
    credentials.get.return_value = CredentialFound(credential=connection().command.credential)
    resolver: DownstreamRuntimeResolver = SharedDownstreamRuntimeResolver(
        CapabilityAvailability(
            UnrestrictedCapabilityPublication(), UnrestrictedCapabilityActivation(),
            readiness, UnrestrictedCapabilityPermissionPolicy(),
        ), definitions, credentials,
    )
    wrong_identity = CapabilityIdentity.model_validate({**identity().model_dump(), **changes})
    with pytest.raises(DownstreamRuntimeUnavailable):
        await resolver.resolve(wrong_identity)


def test_shared_runtime_connection_is_validated_and_frozen() -> None:
    shared = connection()
    with pytest.raises(ValidationError):
        shared.command = shared.command
    with pytest.raises(ValidationError):
        SharedRuntimeConnection(command=DiscoverDownstreamTools(
            definition=shared.command.definition,
            credential=NoAuthCredentialState(connector_id="other"),
        ))
    with pytest.raises(ValidationError):
        SharedRuntimeConnection(command=DiscoverDownstreamTools(
            definition=OAuthConnectorDefinition(
                connector_id="alpha", display_name="Alpha", endpoint_url="https://alpha.example/mcp",
                authorization_mode="personal",
            ), credential=shared.command.credential,
        ))
