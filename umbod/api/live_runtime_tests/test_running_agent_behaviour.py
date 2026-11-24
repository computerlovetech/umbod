import json
from uuid import uuid4

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from conftest import RuntimeEndpoints


@pytest.mark.asyncio
async def test_running_admin_publication_mcp_reporting_and_admin_inspection_share_durable_state(runtime_endpoints: RuntimeEndpoints) -> None:
    suffix = uuid4().hex
    pattern_id = f"context-{suffix}"
    playbook_id = f"review-{suffix}"
    base = "/api/admin/agent-behaviour"
    headers = {"Authorization": f"Bearer {runtime_endpoints.bearer_token}"}
    transport = StreamableHttpTransport(runtime_endpoints.mcp_url, headers=headers)
    async with httpx.AsyncClient(base_url=runtime_endpoints.api_base_url, headers=headers, timeout=30) as api:
        original_response = await api.get(f"{base}/configuration")
        assert original_response.status_code == 200, original_response.text
        original = original_response.json()
        defaults = await api.get(f"{base}/defaults")
        assert defaults.status_code == 200, defaults.text
        assert defaults.headers["cache-control"] == "no-store"
        catalog = defaults.json()
        assert catalog["revision"] == 1
        assert {item["id"] for item in catalog["patterns"]} == {"missing-context", "tool-problems", "task-blocked", "user-correction"}
        assert all(item["enabled"] for item in catalog["patterns"])
        assert len(catalog["playbooks"]) == 1
        assert catalog["playbooks"][0]["id"] == "behaviour-review"
        assert catalog["playbooks"][0]["enabled"] is True
        assert catalog["playbooks"][0]["allow_proactive"] is False
        assert (await api.get(f"{base}/configuration")).json() == original
        pattern = {
            "id": pattern_id, "name": "Runtime context pattern", "description": "Task context is unavailable",
            "assessment_prompt": "Assess whether missing task context prevented completion",
            "inclusion_criteria": "Unavailable task context", "exclusion_criteria": "Ordinary clarifying questions",
            "categories": ["quality"], "polarity": "negative", "enabled": True,
        }
        playbook = {
            "id": playbook_id, "name": "Runtime review", "collection_instructions": "Review only the authorized task context",
            "pattern_ids": [pattern_id], "enabled": True, "allow_proactive": False,
        }
        published = await api.put(f"{base}/configuration", json={"expected_revision": original["revision"], "patterns": [*original["patterns"], pattern], "playbooks": [*original["playbooks"], playbook]})
        assert published.status_code == 200, published.text
        report_ids: list[str] = []
        try:
            revision = published.json()["revision"]
            assert revision == original["revision"] + 1
            assert (await api.get(f"{base}/defaults")).json() == catalog
            assert (await api.get(f"{base}/configuration")).json() == published.json()
            async with Client(transport, mode="legacy") as client:
                instructions = await client.read_resource(f"umbod://agent-behaviour/playbooks/{playbook_id}")
                decoded = json.loads(instructions[0].text)
                assert decoded["configuration_revision"] == revision
                assert decoded["patterns"][0]["assessment_prompt"] == pattern["assessment_prompt"]
                prompt = await client.get_prompt("run_diagnostics", {"playbook_id": playbook_id})
                assert decoded["resource_uri"] in prompt.messages[0].content.text
                assert decoded["playbook"]["collection_instructions"] == playbook["collection_instructions"]
                assert "trigger=user_requested" in decoded["reporting_guidance"]
                command = {
                    "idempotency_key": str(uuid4()), "configuration_revision": revision, "playbook_id": playbook_id,
                    "trigger": "user_requested", "assessments": [{"pattern_id": pattern_id, "status": "observed", "summary": "A required task specification was unavailable", "evidence": ["The task specification could not be provided"]}],
                }
                result = await client.call_tool("report_diagnostic", command)
                assert result.is_error is False
                receipt = result.structured_content
                assert receipt is not None
                report_ids.append(receipt["report_id"])
                detail = await api.get(f"{base}/reports/{receipt['report_id']}")
                assert detail.status_code == 200, detail.text
                assert detail.headers["cache-control"] == "no-store"
                report = detail.json()
                assert report["submission"] == command
                assert report["instructions"]["patterns"][0] == pattern
                assert report["caller"]["subject"]["subject"]
                personal_request = api.build_request("GET", f"/api/me/agent-behaviour/reports/{receipt['report_id']}")
                del personal_request.headers["authorization"]
                personal_detail = await api.send(personal_request)
                assert personal_detail.status_code == 200, personal_detail.text
                assert personal_detail.json()["report_id"] == receipt["report_id"]
                changed_playbook = {**playbook, "collection_instructions": "Use the revised centrally managed review instructions"}
                before_change = await api.get(f"{base}/configuration")
                assert before_change.status_code == 200, before_change.text
                current_configuration = before_change.json()
                changed = await api.put(f"{base}/configuration", json={"expected_revision": current_configuration["revision"], "patterns": current_configuration["patterns"], "playbooks": [changed_playbook if item["id"] == playbook_id else item for item in current_configuration["playbooks"]]})
                assert changed.status_code == 200, changed.text
                refreshed = await client.read_resource(f"umbod://agent-behaviour/playbooks/{playbook_id}")
                assert json.loads(refreshed[0].text)["playbook"]["collection_instructions"] == changed_playbook["collection_instructions"]
                duplicate = await client.call_tool("report_diagnostic", command)
                assert duplicate.structured_content == {**receipt, "duplicate": True}
                rejected = await client.call_tool("report_diagnostic", {**command, "idempotency_key": str(uuid4())}, raise_on_error=False)
                assert rejected.is_error is True
                assert "stale_configuration" in str(rejected.content)
                retained = await api.get(f"{base}/reports/{receipt['report_id']}")
                assert retained.json()["instructions"]["playbook"]["collection_instructions"] == playbook["collection_instructions"]
        finally:
            for report_id in report_ids:
                await api.delete(f"{base}/reports/{report_id}")
            current = await api.get(f"{base}/configuration")
            assert current.status_code == 200, current.text
            current_configuration = current.json()
            restored = await api.put(f"{base}/configuration", json={"expected_revision": current_configuration["revision"], "patterns": [item for item in current_configuration["patterns"] if item["id"] != pattern_id], "playbooks": [item for item in current_configuration["playbooks"] if item["id"] != playbook_id]})
            assert restored.status_code == 200, restored.text
