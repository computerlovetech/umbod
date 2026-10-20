"""Validated, backend-owned settings. Changes apply only at process composition."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool


class DesktopSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_tool_exposure_mode: Literal["gateway", "flat", "codemode"] = "gateway"
    mcp_administrator_enabled: StrictBool = False
