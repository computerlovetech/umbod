"""Validated host requests contain credential references, never secret values."""

from urllib.parse import urlsplit


def loopback_origin(address: str) -> str:
    parsed = urlsplit("http://" + address)
    if (
        parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.port is None
    ):
        raise ValueError("Invalid loopback endpoint")
    return f"http://127.0.0.1:{parsed.port}"
