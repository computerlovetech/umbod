from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, Self, TypeIs

from pydantic import BaseModel as PydanticModel
from pydantic.fields import FieldInfo


class ModelDumpProtocol(Protocol):
    def model_dump(self, **kwargs: Any) -> dict[str, Any]: ...


class ModelSchemaProtocol(Protocol):
    model_fields: ClassVar[Mapping[str, FieldInfo]]

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> Self: ...

    @classmethod
    def model_json_schema(cls, **kwargs: Any) -> dict[str, Any]: ...


class Model(PydanticModel):
    pass


def is_pydantic_model_class(value: object) -> TypeIs[type[PydanticModel]]:
    return isinstance(value, type) and issubclass(value, PydanticModel)


__all__ = [
    "Model",
    "ModelDumpProtocol",
    "ModelSchemaProtocol",
    "PydanticModel",
    "is_pydantic_model_class",
]
