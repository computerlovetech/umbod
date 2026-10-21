from typing import Any

import pytest
from fakes import MemoryAdministration, MemoryNamingPolicy, MemoryState

from umbod_desktop.backward_compatibility.tool_names import DesktopToolNames
from umbod_desktop.contracts import AdministrationError, ConnectorDefinition

LEGACY = "desktop_46b824c3_b082_4a1a_8177_c2c096eec4ce"


def definition(
    identifier: str, name: str, prefix: str = LEGACY, path: str = ""
) -> ConnectorDefinition:
    return ConnectorDefinition(
        connector_id=identifier, display_name=name, tool_name_prefix=prefix,
        public_path=path or "/mcp/proxies/" + prefix.replace("_", "-"),
    )


def managed(*identifiers: str) -> MemoryState:
    return MemoryState({"servers": {key: {"id": key} for key in identifiers}})


def administration(*definitions: ConnectorDefinition, rejected: tuple[str, ...] = ()) -> MemoryAdministration:
    admin = MemoryAdministration(definitions)
    admin.rejected = set(rejected)
    return admin


@pytest.mark.asyncio
async def test_repairs_only_managed_generated_prefixes_and_is_idempotent() -> None:
    admin = administration(
        definition("dinero", "Dinero"),
        definition("imported", "Cloudflare", "import_" + "a" * 24),
        definition("custom", "Dinero", "my_finance"),
        definition("unmanaged", "External"),
        definition("different_path", "Deliberate", path="/mcp/proxies/custom"),
    )
    state = managed("dinero", "imported", "custom", "different_path")
    names = DesktopToolNames(admin, MemoryNamingPolicy(), admin)
    await names.repair(state)
    assert admin.patches == [
        ("dinero", {"tool_name_prefix": "Dinero"}),
        ("imported", {"tool_name_prefix": "Cloudflare"}),
    ]
    assert admin.definitions["dinero"].public_path == "/mcp/proxies/" + LEGACY.replace("_", "-")
    await names.repair(state)
    assert len(admin.patches) == 2


@pytest.mark.asyncio
async def test_duplicate_names_receive_readable_stable_suffixes() -> None:
    admin = administration(
        definition("a", "Finance API"),
        definition("b", "Finance API"),
        definition("custom", "Other", "Finance-API"),
    )
    names = DesktopToolNames(admin, MemoryNamingPolicy(), admin)
    await names.repair(managed("a", "b"))
    assert admin.patches == [
        ("a", {"tool_name_prefix": "Finance_API_2"}),
        ("b", {"tool_name_prefix": "Finance_API_3"}),
    ]
    await names.repair(managed("a", "b"))
    assert len(admin.patches) == 2


@pytest.mark.asyncio
async def test_inventory_failure_does_not_block_startup_and_retries(caplog: Any) -> None:
    class UnavailableAdministration(MemoryAdministration):
        async def inventory(self) -> tuple[ConnectorDefinition, ...]:
            raise AdministrationError()

    admin = UnavailableAdministration((definition("a", "Dinero"),))
    await DesktopToolNames(admin, MemoryNamingPolicy(), admin).repair(managed("a"))
    assert not admin.patches
    assert "retry on restart" in caplog.text
    working = administration(definition("a", "Dinero"))
    await DesktopToolNames(working, MemoryNamingPolicy(), working).repair(managed("a"))
    assert working.definitions["a"].tool_name_prefix == "Dinero"


@pytest.mark.asyncio
async def test_rejected_repair_preserves_working_prefix_and_continues(caplog: Any) -> None:
    admin = administration(
        definition("a", "Dinero"), definition("b", "Cloudflare"), rejected=("a",)
    )
    await DesktopToolNames(admin, MemoryNamingPolicy(), admin).repair(managed("a", "b"))
    assert admin.definitions["a"].tool_name_prefix == LEGACY
    assert admin.definitions["b"].tool_name_prefix == "Cloudflare"
    assert "repair deferred for connector a" in caplog.text
