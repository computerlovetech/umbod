import hashlib
import json

from umbod.core.connectors.downstream_mcp.models import ToolCatalogSnapshot


def catalog_revision(snapshot: ToolCatalogSnapshot) -> str:
    payload = json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
