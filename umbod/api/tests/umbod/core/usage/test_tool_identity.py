import re

import pytest

from umbod.core.usage.models import BuiltinUsageToolTarget, ConnectorUsageToolTarget, UsageTool, usage_tool_id


def connector(identifier: str, kind: str = 'native', capability: str = 'read') -> ConnectorUsageToolTarget:
    return ConnectorUsageToolTarget(kind='connector', connector_kind=kind, connector_id=identifier, capability_key=capability)


def test_identity_is_stable_across_display_renames_and_aliases() -> None:
    target = connector('full-connector-id')
    original = UsageTool(target=target, tool_name='read_alias', connector_name='Old')
    renamed = UsageTool(target=target, tool_name='new_alias', connector_name='New')
    assert usage_tool_id(original.target) == usage_tool_id(renamed.target)
    assert re.fullmatch('[0-9a-f]{64}', usage_tool_id(target))


@pytest.mark.parametrize('other', [
    connector('id-b'), connector('id-a', kind='openapi'),
    connector('id-a', capability='write'), connector('id-a' + 'x' * 300),
    BuiltinUsageToolTarget(kind='builtin', registered_name='read'),
])
def test_canonical_identity_separates_connectors_kinds_and_capabilities(
    other: ConnectorUsageToolTarget | BuiltinUsageToolTarget,
) -> None:
    assert usage_tool_id(connector('id-a')) != usage_tool_id(other)


def test_full_connector_identity_is_not_truncated() -> None:
    assert usage_tool_id(connector('x' * 256 + 'a')) != usage_tool_id(connector('x' * 256 + 'b'))


def test_versioned_identity_hash_has_stable_known_value() -> None:
    assert usage_tool_id(BuiltinUsageToolTarget(kind='builtin', registered_name='files')) == (
        'ce903b00633cdad56035836e00cccd289c43e737fd5203fa77174fd6adf9a495'
    )


def test_structured_identity_does_not_collide_on_delimiters() -> None:
    assert usage_tool_id(connector('a:b', capability='c')) != usage_tool_id(connector('a', capability='b:c'))
