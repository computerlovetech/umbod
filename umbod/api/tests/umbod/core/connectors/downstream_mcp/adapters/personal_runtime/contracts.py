from umbod.core.connectors.downstream_mcp.models import DiscoveredToolWithoutOutputSchema, ToolIdentity
from umbod.core.connectors.downstream_mcp.personal_tools import contract_fingerprint

LOOKUP_TOOL = DiscoveredToolWithoutOutputSchema(identity=ToolIdentity(connector_id="connector", downstream_name="lookup"), title="lookup", description="", input_schema={"type": "object"})
LOOKUP_FINGERPRINT = contract_fingerprint(LOOKUP_TOOL)
