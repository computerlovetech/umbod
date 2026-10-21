from typing import Literal

from mcp import types
from pydantic import ConfigDict, Field


class StrictCallToolResult(types.CallToolResult):
    model_config = ConfigDict(extra="forbid", strict=True)

    content: list[types.ContentBlock] = Field(...)
    result_type: Literal["complete"] = "complete"
