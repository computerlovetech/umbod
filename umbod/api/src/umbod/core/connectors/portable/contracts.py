from dataclasses import dataclass
from json import loads
from typing import Any, Literal, NotRequired, TypedDict


class PortableTool(TypedDict):
    operation_name: str
    handler_id: str
    description: str
    input_schema: dict[str, Any]
    output_schema: NotRequired[dict[str, Any]]


class PortableManifest(TypedDict):
    manifest_version: Literal[1, 2]
    connector_id: str
    display_name: str
    description: str
    capability_description: str
    configuration_schema: dict[str, Any]
    configuration_check_handler_id: str
    tools: list[PortableTool]
    http_targets: NotRequired[dict[str, str]]


@dataclass(frozen=True, slots=True)
class PreparedPortableConnector:
    source: str
    _source_digest: bytes
    _manifest_json: str

    @property
    def manifest(self) -> PortableManifest:
        return loads(self._manifest_json)


@dataclass(frozen=True, slots=True)
class PortableHttpAccess:
    approved_targets: frozenset[str]
    approved_post_paths: frozenset[tuple[str, tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class PortableExecutionLimits:
    deadline_seconds: float
    max_http_calls: int
