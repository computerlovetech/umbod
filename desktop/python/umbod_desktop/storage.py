"""Owner-only durable host metadata, separate from shared connector storage."""

import json
from pathlib import Path

from pydantic import ValidationError

from .persistence import atomic_bytes as atomic_bytes
from .persistence import atomic_json as atomic_json
from .settings import DesktopSettings


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
