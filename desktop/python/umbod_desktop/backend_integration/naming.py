from umbod.core.capabilities.tools.names import mangle_public_tool_name
from umbod.core.connectors.downstream_mcp.models import default_tool_name_prefix


class BackendToolNamingPolicy:
    def readable_prefix(self, display_name: str) -> str:
        return default_tool_name_prefix(display_name)

    def collision_key(self, prefix: str) -> str:
        return mangle_public_tool_name(prefix, "")
