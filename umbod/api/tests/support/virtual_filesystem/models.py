from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Union


@dataclass(frozen=True)
class NodeHandle:
    value: str


@dataclass(frozen=True)
class MetadataValue:
    content_type: str
    attributes: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


@dataclass(frozen=True)
class UntypedMetadataValue:
    attributes: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "attributes", MappingProxyType(dict(self.attributes)))


Metadata = Union[MetadataValue, UntypedMetadataValue]


@dataclass(frozen=True)
class NodeView:
    node: NodeHandle
    name: str
    kind: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: Metadata


@dataclass(frozen=True)
class ContentHandle:
    value: str


@dataclass(frozen=True)
class StoredContentView:
    content: ContentHandle
    size: int


@dataclass(frozen=True)
class NoContentReference:
    pass
