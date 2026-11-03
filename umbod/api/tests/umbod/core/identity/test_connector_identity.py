import pytest

from umbod.core.identity import (
    AggregateConnectorIdentityCatalog,
    ConnectorIdentity,
    ConnectorIdentityConflictError,
)


class StaticIdentitySource:
    def __init__(self, *identities: ConnectorIdentity) -> None:
        self._identities = identities

    async def identities(self) -> tuple[ConnectorIdentity, ...]:
        return self._identities


@pytest.mark.parametrize("existing_type", ["built_in", "openapi", "downstream_mcp"])
@pytest.mark.asyncio
async def test_cross_type_connector_id_conflict_is_rejected(existing_type: str) -> None:
    catalog = AggregateConnectorIdentityCatalog(
        (
            StaticIdentitySource(
                ConnectorIdentity(connector_id="shared", connector_type=existing_type)
            ),
        )
    )

    with pytest.raises(ConnectorIdentityConflictError) as captured:
        await catalog.ensure_available(
            ConnectorIdentity(connector_id="shared", connector_type="downstream_mcp")
        )

    assert captured.value.existing.connector_type == existing_type
