import json
from collections.abc import Callable
from pathlib import Path


def validate_saved_port(port: object) -> int:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid saved local port")
    return port


def no_saved_port(directory: Path) -> int:
    return 0


def saved_port(directory: Path, fallback: Callable[[Path], int]) -> int:
    path = directory / "python-endpoint.json"
    if path.exists():
        port = json.loads(path.read_text()).get("port")
        if port is not None:
            return validate_saved_port(port)
    return fallback(directory)
