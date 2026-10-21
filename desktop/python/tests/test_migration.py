import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fakes import (
    MemoryAdministration,
    MemoryAuthorizationImporter,
    MemoryNamingPolicy,
    MemoryState,
    MemoryUpstreams,
)

from umbod_desktop.backward_compatibility.migration import DesktopMigration
from umbod_desktop.backward_compatibility.tool_names import DesktopToolNames
from umbod_desktop.contracts import ConnectorCreation, ConnectorDefinition
from umbod_desktop.ports import ConnectorAdministration, MetadataState


def migration(
    directory: Path, state: MetadataState, administration: ConnectorAdministration,
    upstreams: MemoryUpstreams, importer: MemoryAuthorizationImporter,
) -> DesktopMigration:
    return DesktopMigration(
        directory, state, upstreams, administration,
        DesktopToolNames(administration, MemoryNamingPolicy(), administration), importer,
    )


def legacy_source(directory: Path, extra: dict[str, Any]) -> bytes:
    source = json.dumps({
        "servers": [{"id": "legacy", "name": "Finance API", "transport": "http", "url": "https://tools.example/mcp", "oauth": True}],
        **extra,
    }).encode()
    (directory / "config.json").write_bytes(source)
    return source


async def test_resume_after_discovery_failure_preserves_journal_and_credentials(tmp_path: Path) -> None:
    class InterruptedAdministration(MemoryAdministration):
        async def discover(self, connector_id: str) -> None:
            if not self.discovered:
                self.discovered.append(connector_id)
                raise OSError("private-secret")
            await super().discover(connector_id)

    source = legacy_source(tmp_path, {"allowed_tools": ["legacy.read"]})
    state = MemoryState({"servers": {}})
    admin = InterruptedAdministration(())
    upstreams = MemoryUpstreams()
    importer = MemoryAuthorizationImporter()
    use_case = migration(tmp_path, state, admin, upstreams, importer)
    await use_case.run()
    entry = state.data["migration"]["connectors"]["legacy"]
    assert entry["id"] == "connector-1"
    assert state.data["migration"]["status"] == "needs_attention"
    assert "private-secret" not in json.dumps(state.data)
    await use_case.run()
    assert state.data["migration"]["status"] == "complete"
    assert len(admin.created) == len(upstreams.prepared) == 1
    assert len(importer.imported) == 2
    assert importer.imported[0].endpoint_url == "https://tools.example/mcp"
    assert admin.enabled[0].names == ("read",)
    assert admin.grants[0].selection == admin.enabled[0]
    assert upstreams.bindings[0].connector_id == "connector-1"
    assert (tmp_path / "config.json").read_bytes() == source
    assert json.loads((tmp_path / "config.before-python.json").read_bytes()) == json.loads(source)
    await use_case.run()
    assert len(admin.published) == 1


async def test_recovers_creation_committed_before_journal_by_stable_path(tmp_path: Path) -> None:
    class CommittedAdministration(MemoryAdministration):
        async def create(self, command: ConnectorCreation) -> ConnectorDefinition:
            await super().create(command)
            raise OSError("reply lost")

    legacy_source(tmp_path, {"allowed_tools": []})
    state = MemoryState({"servers": {}})
    admin = CommittedAdministration(())
    upstreams = MemoryUpstreams()
    use_case = migration(tmp_path, state, admin, upstreams, MemoryAuthorizationImporter())
    await use_case.run()
    assert "id" not in state.data["migration"]["connectors"]["legacy"]
    await use_case.run()
    assert state.data["migration"]["status"] == "complete"
    assert len(admin.created) == len(upstreams.prepared) == 1
    assert upstreams.bindings[0].connector_id == "connector-1"
    assert not admin.enabled
    assert not admin.grants


@pytest.mark.parametrize("clients,grants,selected", [
    ([{"id": "a"}, {"id": "b"}], {"a": ["legacy.read", "legacy.write"], "b": ["legacy.read"]}, ("read",)),
    ([{"id": "a"}, {"id": "b"}], {"a": ["legacy.read"]}, ()),
    ([], {}, ()),
])
async def test_migration_grants_only_intersection(
    tmp_path: Path, clients: list[dict[str, str]], grants: dict[str, list[str]], selected: tuple[str, ...],
) -> None:
    legacy_source(tmp_path, {"clients": clients, "grants": grants})
    state = MemoryState({"servers": {}})
    admin = MemoryAdministration(())
    await migration(tmp_path, state, admin, MemoryUpstreams(), MemoryAuthorizationImporter()).run()
    assert state.data["migration"]["status"] == "complete"
    assert [selection.names for selection in admin.enabled] == ([selected] if selected else [])
    assert [grant.selection.names for grant in admin.grants] == ([selected] if selected else [])
    assert admin.published == ["connector-1"]


async def test_cancellation_propagates_and_saves_retryable_journal(tmp_path: Path) -> None:
    class CancelledAdministration(MemoryAdministration):
        async def discover(self, connector_id: str) -> None:
            raise asyncio.CancelledError()

    legacy_source(tmp_path, {})
    state = MemoryState({"servers": {}})
    use_case = migration(tmp_path, state, CancelledAdministration(()), MemoryUpstreams(), MemoryAuthorizationImporter())
    with pytest.raises(asyncio.CancelledError):
        await use_case.run()
    assert state.data["migration"]["status"] == "importing"
    assert "error" not in state.data["migration"]
    assert state.saves > 0


async def test_changed_source_is_rejected_without_overwriting_backup(tmp_path: Path) -> None:
    class FailingAdministration(MemoryAdministration):
        async def discover(self, connector_id: str) -> None:
            raise OSError("private-access-token")

    source = legacy_source(tmp_path, {})
    state = MemoryState({"servers": {}})
    use_case = migration(tmp_path, state, FailingAdministration(()), MemoryUpstreams(), MemoryAuthorizationImporter())
    await use_case.run()
    legacy_source(tmp_path, {"allowed_tools": []})
    with pytest.raises(ValueError, match="Legacy settings changed"):
        await use_case.run()
    assert json.loads((tmp_path / "config.before-python.json").read_bytes()) == json.loads(source)
    assert "private-access-token" not in json.dumps(state.data)
