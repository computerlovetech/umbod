from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Generic, Protocol, TypeAlias, TypeVar, cast
from pydantic import BaseModel, ConfigDict


RowT = TypeVar("RowT", bound=BaseModel)
KeyT = TypeVar("KeyT", bound=BaseModel)
ValueT = TypeVar("ValueT")
ResultT = TypeVar("ResultT", bound=BaseModel)


class PersistenceDecodingError(ValueError):
    def __init__(self, table_name: str, field_name: str, reason: Exception) -> None:
        super().__init__(f"Failed to decode {table_name}.{field_name}: {reason}")
        self.table_name = table_name
        self.field_name = field_name


class ColumnType(str, Enum):
    TEXT = "text"
    NULLABLE_TEXT = "nullable_text"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    JSON = "json"


class ColumnCodec(Protocol, Generic[ValueT]):
    column_type: ClassVar[ColumnType]

    def encode(self, value: ValueT) -> object: ...

    def decode(self, value: object) -> ValueT: ...


@dataclass(frozen=True)
class TextCodec(ColumnCodec[str]):
    column_type: ClassVar[ColumnType] = ColumnType.TEXT

    def encode(self, value: str) -> object:
        if not isinstance(value, str):
            raise TypeError("expected str")
        return value

    def decode(self, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("expected stored text")
        return value


@dataclass(frozen=True)
class IntegerCodec(ColumnCodec[int]):
    column_type: ClassVar[ColumnType] = ColumnType.INTEGER

    def encode(self, value: int) -> object:
        return _portable_integer(value)

    def decode(self, value: object) -> int:
        try:
            return _portable_integer(value)
        except TypeError as error:
            raise TypeError("expected stored integer") from error


@dataclass(frozen=True)
class BooleanCodec(ColumnCodec[bool]):
    column_type: ClassVar[ColumnType] = ColumnType.BOOLEAN

    def encode(self, value: bool) -> object:
        if not isinstance(value, bool):
            raise TypeError("expected bool")
        return value

    def decode(self, value: object) -> bool:
        if not isinstance(value, bool):
            raise TypeError("expected bool")
        return value


@dataclass(frozen=True)
class JsonValueCodec(ColumnCodec[ValueT], Generic[ValueT]):
    column_type: ClassVar[ColumnType] = ColumnType.JSON

    def encode(self, value: ValueT) -> object:
        return cast(ValueT, _canonical_json(value))

    def decode(self, value: object) -> ValueT:
        return cast(ValueT, _canonical_json(value))


@dataclass(frozen=True)
class JsonTupleCodec(ColumnCodec[tuple[ValueT, ...]], Generic[ValueT]):
    column_type: ClassVar[ColumnType] = ColumnType.JSON

    def encode(self, value: tuple[ValueT, ...]) -> object:
        if not isinstance(value, tuple):
            raise TypeError("expected tuple")
        encoded = _canonical_json(value)
        if not isinstance(encoded, list):
            raise TypeError("expected JSON array")
        return encoded

    def decode(self, value: object) -> tuple[ValueT, ...]:
        decoded = _canonical_json(value)
        if not isinstance(decoded, list):
            raise TypeError("expected JSON array")
        return tuple(cast(list[ValueT], decoded))


ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class PydanticJsonCodec(ColumnCodec[ModelT], Generic[ModelT]):
    model_type: type[ModelT]
    column_type: ClassVar[ColumnType] = ColumnType.JSON

    def encode(self, value: ModelT) -> object:
        if not isinstance(value, self.model_type):
            raise TypeError(f"expected {self.model_type.__name__}")
        return _canonical_json(value.model_dump(mode="json"))

    def decode(self, value: object) -> ModelT:
        return self.model_type.model_validate(_canonical_json(value))


_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _validate_identifier(value: str) -> None:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid persistence identifier: {value!r}")


def _portable_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected int")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError("expected signed 64-bit integer")
    return value


def _canonical_json(value: object) -> object:
    try:
        serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return json.loads(serialized)
    except (TypeError, ValueError) as error:
        raise TypeError("expected JSON-compatible value") from error


@dataclass(frozen=True)
class TableIdentity:
    name: str

    def __post_init__(self) -> None:
        _validate_identifier(self.name)


@dataclass(frozen=True)
class Field(Generic[RowT, ValueT]):
    table_identity: TableIdentity
    name: str
    codec: ColumnCodec[ValueT]

    def __post_init__(self) -> None:
        _validate_identifier(self.name)


@dataclass(frozen=True)
class RowCodec(Generic[RowT]):
    model_type: type[RowT]
    fields: tuple[Field[RowT, object], ...]


@dataclass(frozen=True)
class KeyCodec(Generic[RowT, KeyT]):
    model_type: type[KeyT]
    fields: tuple[Field[RowT, object], ...]


@dataclass(frozen=True)
class Table(Generic[RowT, KeyT]):
    identity: TableIdentity
    row_codec: RowCodec[RowT]
    key_codec: KeyCodec[RowT, KeyT]

    def __post_init__(self) -> None:
        row_fields = self.row_codec.fields
        key_fields = self.key_codec.fields
        if not row_fields:
            raise ValueError(f"Table {self.name} requires row fields")
        if not key_fields:
            raise ValueError(f"Table {self.name} requires key fields")
        if any(field.table_identity != self.identity for field in row_fields + key_fields):
            raise ValueError(f"Table {self.name} fields must share its identity")
        if len({field.name for field in row_fields}) != len(row_fields):
            raise ValueError(f"Table {self.name} requires unique row fields")
        if any(field not in row_fields for field in key_fields):
            raise ValueError(f"Table {self.name} key fields must belong to its row fields")
        if any(field.codec.column_type is ColumnType.JSON for field in key_fields):
            raise ValueError(f"Table {self.name} does not support JSON key fields")

    @property
    def name(self) -> str:
        return self.identity.name


@dataclass(frozen=True)
class NoFilter(Generic[RowT]):
    pass


@dataclass(frozen=True)
class Equals(Generic[RowT, ValueT]):
    field: Field[RowT, ValueT]
    value: ValueT


@dataclass(frozen=True)
class OneOf(Generic[RowT, ValueT]):
    field: Field[RowT, ValueT]
    values: tuple[ValueT, ...]


@dataclass(frozen=True)
class GreaterThan(Generic[RowT, ValueT]):
    field: Field[RowT, ValueT]
    value: ValueT


@dataclass(frozen=True)
class Not(Generic[RowT]):
    predicate: "Predicate[RowT]"


@dataclass(frozen=True)
class AllOf(Generic[RowT]):
    predicates: tuple["Predicate[RowT]", ...]


@dataclass(frozen=True)
class AnyOf(Generic[RowT]):
    predicates: tuple["Predicate[RowT]", ...]


Predicate: TypeAlias = (
    NoFilter[RowT]
    | Equals[RowT, object]
    | OneOf[RowT, object]
    | GreaterThan[RowT, object]
    | Not[RowT]
    | AllOf[RowT]
    | AnyOf[RowT]
)


@dataclass(frozen=True)
class AllFields(Generic[RowT]):
    pass


@dataclass(frozen=True)
class Fields(Generic[RowT, ResultT]):
    result_type: type[ResultT]
    fields: tuple[Field[RowT, object], ...]

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("Fields requires at least one field")


Projection: TypeAlias = AllFields[RowT] | Fields[RowT, ResultT]


@dataclass(frozen=True)
class Unordered(Generic[RowT]):
    pass


@dataclass(frozen=True)
class OrderBy(Generic[RowT]):
    fields: tuple[Field[RowT, object], ...]

    def __post_init__(self) -> None:
        if not self.fields:
            raise ValueError("OrderBy requires at least one field")


Ordering: TypeAlias = Unordered[RowT] | OrderBy[RowT]


@dataclass(frozen=True)
class Query(Generic[RowT, ResultT]):
    filter: Predicate[RowT]
    projection: Projection[RowT, ResultT]
    ordering: Ordering[RowT]
    limit: int | None = None

    def __post_init__(self) -> None:
        if self.limit is not None and (
            not isinstance(self.limit, int) or isinstance(self.limit, bool)
        ):
            raise TypeError("Query limit must be an integer")
        if self.limit is not None and self.limit < 0:
            raise ValueError("Query limit cannot be negative")


@dataclass(frozen=True)
class DeleteQuery(Generic[RowT]):
    filter: Predicate[RowT]


class InsertCommand(BaseModel, Generic[RowT]):
    model_config = ConfigDict(frozen=True)
    row: RowT


@dataclass(frozen=True)
class GeneratedIntegerKeyInsertCommand(Generic[RowT]):
    row: RowT
    generated_field: Field[RowT, int]


class UpsertCommand(BaseModel, Generic[RowT, KeyT]):
    model_config = ConfigDict(frozen=True)
    key: KeyT
    row: RowT


def validate_query(
    table: Table[RowT, KeyT], query: Query[RowT, ResultT] | DeleteQuery[RowT]
) -> None:
    fields = tuple(_predicate_fields(query.filter))
    if isinstance(query, Query):
        if isinstance(query.projection, Fields):
            fields += query.projection.fields
        if isinstance(query.ordering, OrderBy):
            fields += query.ordering.fields
    for field_descriptor in fields:
        if field_descriptor.table_identity != table.identity:
            raise ValueError(f"Field {field_descriptor.name} does not belong to table {table.name}")
    _validate_predicate_values(query.filter)
    _validate_comparable_fields(query)


def _encode_model(
    table: Table[RowT, KeyT], model: BaseModel, fields: tuple[Field[RowT, object], ...]
) -> dict[str, object]:
    values: dict[str, object] = {}
    for field_descriptor in fields:
        try:
            values[field_descriptor.name] = field_descriptor.codec.encode(
                getattr(model, field_descriptor.name)
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise TypeError(
                f"Invalid value for {table.name}.{field_descriptor.name}: {error}"
            ) from error
    return values


def _decode_result(
    table: Table[RowT, KeyT], values: Mapping[str, object], projection: Projection[RowT, ResultT]
) -> RowT | ResultT:
    fields = table.row_codec.fields if isinstance(projection, AllFields) else projection.fields
    decoded: dict[str, object] = {}
    for field_descriptor in fields:
        try:
            decoded[field_descriptor.name] = field_descriptor.codec.decode(
                values[field_descriptor.name]
            )
        except (KeyError, TypeError, ValueError) as error:
            raise PersistenceDecodingError(table.name, field_descriptor.name, error) from error
    model_type = (
        table.row_codec.model_type if isinstance(projection, AllFields) else projection.result_type
    )
    try:
        return model_type.model_validate(decoded)
    except ValueError as error:
        raise PersistenceDecodingError(table.name, "<result>", error) from error


def _predicate_fields(predicate: Predicate[RowT]) -> tuple[Field[RowT, object], ...]:
    if isinstance(predicate, NoFilter):
        return ()
    if isinstance(predicate, (Equals, OneOf, GreaterThan)):
        return (cast(Field[RowT, object], predicate.field),)
    if isinstance(predicate, Not):
        return _predicate_fields(predicate.predicate)
    return tuple(field for child in predicate.predicates for field in _predicate_fields(child))


def _validate_comparable_fields(
    query: Query[RowT, ResultT] | DeleteQuery[RowT],
) -> None:
    fields = _predicate_fields(query.filter)
    if isinstance(query, Query) and isinstance(query.ordering, OrderBy):
        fields += query.ordering.fields
    for field_descriptor in fields:
        if field_descriptor.codec.column_type is ColumnType.JSON:
            raise ValueError(
                f"JSON field {field_descriptor.name} does not support filtering or ordering"
            )


def _validate_predicate_values(predicate: Predicate[RowT]) -> None:
    if isinstance(predicate, (Equals, GreaterThan)):
        predicate.field.codec.encode(predicate.value)
    elif isinstance(predicate, OneOf):
        for value in predicate.values:
            predicate.field.codec.encode(value)
    elif isinstance(predicate, Not):
        _validate_predicate_values(predicate.predicate)
    elif isinstance(predicate, (AllOf, AnyOf)):
        for child in predicate.predicates:
            _validate_predicate_values(child)
