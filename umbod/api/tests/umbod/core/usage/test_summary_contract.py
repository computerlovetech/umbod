import pytest
from pydantic import ValidationError

from umbod.core.usage.models import UsageTopTool


@pytest.mark.parametrize('changes', [
    {'tool_id': 'A' * 64}, {'tool_id': 'a' * 63}, {'tool_name': ''},
    {'connector_name': ''}, {'count': 0}, {'tool_name': 'x' * 257},
])
def test_top_tool_contract_rejects_invalid_values(changes: dict[str, str | int]) -> None:
    payload: dict[str, str | int] = {
        'tool_id': 'a' * 64, 'tool_name': 'Files', 'connector_name': 'Umbod', 'count': 1,
    }
    payload.update(changes)
    with pytest.raises(ValidationError):
        UsageTopTool.model_validate(payload)
