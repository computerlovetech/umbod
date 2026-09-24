from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel
from pydantic.fields import FieldInfo


class ModelDumpProtocol(Protocol):
    def model_dump(self, **kwargs: Any) -> dict[str, Any]: ...


class ModelSchemaProtocol(Protocol):
    model_fields: ClassVar[Mapping[str, FieldInfo]]

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> Self: ...

    @classmethod
    def model_json_schema(cls, **kwargs: Any) -> dict[str, Any]: ...


class Model(BaseModel):
    pass


__all__ = ["Model", "ModelDumpProtocol", "ModelSchemaProtocol"]
