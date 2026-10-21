import json
import os
import tempfile
from pathlib import Path


def atomic_json(path: Path, value: object) -> None:
    atomic_bytes(path, json.dumps(value).encode())


def atomic_bytes(path: Path, value: bytes) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
