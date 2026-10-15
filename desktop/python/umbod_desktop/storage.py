"""Owner-only durable host metadata, separate from shared connector storage."""

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .settings import DesktopSettings


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


class DesktopState:
    def __init__(self, directory: Path) -> None:
        self.path = directory / "desktop-v2.json"
        self.data = (
            json.loads(self.path.read_text())
            if self.path.exists()
            else {"version": 2, "servers": {}}
        )
        if not isinstance(self.data, dict) or self.data.get("version") != 2:
            raise ValueError("Unsupported desktop state version")
        try:
            self.settings
        except ValidationError:
            raise ValueError(
                "Desktop settings in desktop-v2.json are invalid. Restore valid settings "
                "(gateway, flat or codemode and a boolean administrator switch), then restart. "
                "Your profile has not been reset."
            ) from None

    @property
    def settings(self) -> DesktopSettings:
        return DesktopSettings.model_validate(self.data.get("settings", {}))

    def save(self) -> None:
        atomic_json(self.path, self.data)
