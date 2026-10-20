import logging
import re
from collections.abc import Sequence

from ..contracts import (
    AdministrationError,
    AdministrationRejected,
    ConnectorDefinition,
)
from ..ports import ConnectorAdministration, MetadataState, ToolNamingPolicy
from .contracts import PrefixUpdate
from .ports import PrefixRepair

_LOGGER = logging.getLogger(__name__)
_GENERATED_PREFIX = re.compile(
    r"(?:desktop_[0-9a-f]{8}(?:_[0-9a-f]{4}){3}_[0-9a-f]{12}|import_[0-9a-f]{24})"
)


class DesktopToolNames:
    def __init__(
        self, administration: ConnectorAdministration, policy: ToolNamingPolicy,
        prefix_repair: PrefixRepair,
    ) -> None:
        self.administration = administration
        self.policy = policy
        self.prefix_repair = prefix_repair

    def available_prefix(self, display_name: str, definitions: Sequence[ConnectorDefinition]) -> str:
        base = self.policy.readable_prefix(display_name)
        reserved = {self.policy.collision_key(item.tool_name_prefix) for item in definitions}
        candidate, suffix = base, 2
        while self.policy.collision_key(candidate) in reserved:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    async def repair(self, state: MetadataState) -> None:
        managed_ids = {
            item.get("id") for item in state.data.get("servers", {}).values()
        }
        if not managed_ids:
            return
        try:
            definitions = list(await self.administration.inventory())
            for definition in sorted(definitions, key=lambda item: item.connector_id):
                prefix = definition.tool_name_prefix
                if (
                    definition.connector_id not in managed_ids
                    or not _GENERATED_PREFIX.fullmatch(prefix)
                    or definition.public_path.removeprefix("/mcp/proxies/")
                    .replace("-", "_") != prefix
                ):
                    continue
                candidate = self.available_prefix(definition.display_name, definitions)
                try:
                    await self.prefix_repair.update_prefix(PrefixUpdate(
                        connector_id=definition.connector_id, prefix=candidate,
                    ))
                except AdministrationRejected:
                    _LOGGER.warning(
                        "Desktop tool namespace repair deferred for connector %s",
                        definition.connector_id,
                    )
                    continue
                definitions[definitions.index(definition)] = definition.model_copy(
                    update={"tool_name_prefix": candidate}
                )
        except AdministrationError:
            _LOGGER.warning("Desktop tool namespace repair deferred; retry on restart")
