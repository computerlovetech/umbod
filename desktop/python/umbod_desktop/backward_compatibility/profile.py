import json
from pathlib import Path

from ..endpoint import validate_saved_port


def saved_agent_hashes(directory: Path) -> list[str]:
    path = directory / "config.json"
    if not path.exists():
        return []
    document = json.loads(path.read_text())
    clients = list(document.get("clients", []))
    if document.get("connection"):
        clients.append(document["connection"])
    return sorted(
        {
            client["token_hash"]
            for client in clients
            if isinstance(client.get("token_hash"), str)
            and len(client["token_hash"]) == 64
            and all(c in "0123456789abcdef" for c in client["token_hash"])
        }
    )


def saved_legacy_port(directory: Path) -> int:
    path = directory / "config.json"
    if path.exists():
        port = json.loads(path.read_text()).get("gateway_port")
        if port is not None:
            return validate_saved_port(port)
    return 0
