import asyncio
import hashlib
import json
from pathlib import Path

from ..contracts import (
    DESKTOP_GROUP,
    ConnectorBinding,
    ConnectorCreation,
    ToolGrant,
    ToolSelection,
    UpstreamInput,
)
from ..persistence import atomic_json
from ..ports import (
    ConnectorAdministration,
    MetadataState,
    UpstreamPreparation,
)
from .contracts import LegacyAuthorization
from .ports import LegacyAuthorizationImporter
from .tool_names import DesktopToolNames


class DesktopMigration:
    def __init__(
        self, directory: Path, state: MetadataState, upstreams: UpstreamPreparation,
        administration: ConnectorAdministration, tool_names: DesktopToolNames,
        authorization_importer: LegacyAuthorizationImporter,
    ) -> None:
        self.directory, self.state, self.upstreams = directory, state, upstreams
        self.administration = administration
        self.tool_names = tool_names
        self.authorization_importer = authorization_importer
        self.lock = asyncio.Lock()

    async def run(self) -> None:
        async with self.lock:
            await self._run()

    async def _run(self) -> None:
        source = self.directory / "config.json"
        if (
            not source.exists()
            or self.state.data.get("migration", {}).get("status") == "complete"
        ):
            return
        payload = source.read_bytes()
        legacy = json.loads(payload)
        digest = hashlib.sha256(payload).hexdigest()
        journal = self.state.data.setdefault(
            "migration",
            {"status": "pending", "source_sha256": digest, "connectors": {}},
        )
        if journal["source_sha256"] != digest:
            raise ValueError(
                "Legacy settings changed during migration; restore the saved source before retrying"
            )
        backup = self.directory / "config.before-python.json"
        if not backup.exists():
            atomic_json(backup, legacy)
        journal["status"] = "importing"
        self.state.save()
        try:
            await self.administration.ensure_group(DESKTOP_GROUP)
            for server in legacy.get("servers", []):
                old_id = server["id"]
                entry = journal["connectors"].setdefault(old_id, {})
                if entry.get("complete"):
                    continue
                if "host_id" not in entry:
                    prepared = await self.upstreams.prepare(UpstreamInput(server))
                    entry["host_id"] = prepared.host_id
                    self.state.save()
                host_id = entry["host_id"]
                if server.get("oauth"):
                    self.authorization_importer.import_authorization(LegacyAuthorization(
                        legacy_id=old_id, host_id=host_id, endpoint_url=server["url"]
                    ))
                config = self.upstreams.proxy_configuration(host_id)
                if "id" not in entry:
                    slug = "import-" + hashlib.sha256(old_id.encode()).hexdigest()[:24]
                    definitions = await self.administration.inventory()
                    existing = next((
                        item for item in definitions
                        if item.public_path == f"/mcp/proxies/{slug}"
                    ), None)
                    created = existing or await self.administration.create(ConnectorCreation(
                        display_name=server["name"],
                        tool_name_prefix=self.tool_names.available_prefix(
                            server["name"], await self.administration.inventory()
                        ),
                        capability_description=f"Tools from {server['name']}",
                        public_path=f"/mcp/proxies/{slug}",
                        configuration=config,
                    ))
                    entry["id"] = created.connector_id
                    self.upstreams.bind(ConnectorBinding(host_id=host_id, connector_id=entry["id"]))
                    self.state.save()
                await self.administration.discover(entry["id"])
                tools = await self.administration.tool_names(entry["id"])
                allowed = legacy.get("allowed_tools")
                if allowed is None:
                    client_ids = [client["id"] for client in legacy.get("clients", [])]
                    sets = [
                        set(legacy.get("grants", {}).get(client, []))
                        for client in client_ids
                    ]
                    allowed = set.intersection(*sets) if sets else set()
                selected = ToolSelection(
                    connector_id=entry["id"],
                    names=tuple(name for name in tools if f"{old_id}.{name}" in allowed),
                )
                if selected.names:
                    await self.administration.enable_tools(selected)
                    await self.administration.grant_tools(ToolGrant(
                        group_id=DESKTOP_GROUP, selection=selected
                    ))
                await self.administration.publish(entry["id"])
                entry["complete"] = True
                self.state.save()
            for field in (
                "daily_calls",
                "daily_tracking_started",
                "diagnostics",
                "client_setup",
            ):
                if field in legacy:
                    self.state.data.setdefault(field, legacy[field])
            if legacy.get("activation") and "activation" not in self.state.data:
                journey = dict(legacy["activation"])
                entry = journal["connectors"].get(journey.get("server"), {})
                journey["server"] = entry.get("id", journey.get("server"))
                self.state.data["activation"] = journey
            usage = self.state.data.setdefault("tool_usage", {})
            for name, counts in legacy.get("tool_usage", {}).items():
                old_id, _, tool = name.partition(".")
                new_id = journal["connectors"].get(old_id, {}).get("id", old_id)
                usage.setdefault(f"{new_id}.{tool}", counts)
            journal["status"] = "complete"
            journal.pop("error", None)
        except Exception:
            journal["status"] = "needs_attention"
            journal["error"] = (
                "Some connectors could not be imported. Original settings and credentials are preserved; reconnect the upstream and retry."
            )
        finally:
            self.state.save()
