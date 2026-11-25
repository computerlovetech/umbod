from pathlib import Path

import pytest

from tests.persistence_runtime import create_sqlite_runtime
from tests.support.personal_oauth_setup import SETUP_CALLBACK, install_setup_validation
from umbod.core.connectors.downstream_mcp.management import PublishDownstreamConnectorAggregate
from umbod.core.connectors.downstream_mcp.models import OAuthConnectorDefinition
from umbod.core.connectors.downstream_mcp.personal.oauth.setup.state import PersonalOAuthSetupQuery, SetupValidated
from umbod.core.connectors.downstream_mcp.stores import SaveConnectorDefinition, create_downstream_mcp_stores


@pytest.mark.asyncio
async def test_validation_receipt_survives_runtime_recreation_and_gates_publication(tmp_path: Path) -> None:
    path = tmp_path / "setup.sqlite3"
    writer = create_sqlite_runtime(path)
    query = PersonalOAuthSetupQuery(connector_id="personal", redirect_uri=SETUP_CALLBACK)
    try:
        await writer.readiness.ensure_ready()
        stores = await create_downstream_mcp_stores("durability-test", writer.database)
        await stores.definitions.save(SaveConnectorDefinition(definition=OAuthConnectorDefinition(connector_id="personal", display_name="Personal", endpoint_url="https://tools.example/mcp", authorization_mode="personal")))
        await install_setup_validation(stores, "personal")
        expected = await stores.personal_oauth_setup.get(query)
    finally:
        await writer.shutdown()
    reader = create_sqlite_runtime(path)
    try:
        await reader.readiness.ensure_ready()
        restored = await create_downstream_mcp_stores("durability-test", reader.database)
        actual = await restored.personal_oauth_setup.get(query)
        assert actual == expected
        assert isinstance(actual.state, SetupValidated)
        assert await restored.unit_of_work.publish(PublishDownstreamConnectorAggregate(connector_id="personal", native_identities=(), personal_oauth_redirect_uri=SETUP_CALLBACK))
    finally:
        await reader.shutdown()
