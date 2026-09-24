from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from umbod.core.persistence.query import (
    AllFields,
    AllOf,
    AnyOf,
    ColumnType,
    DeleteQuery,
    Equals,
    GeneratedIntegerKeyInsertCommand,
    GreaterThan,
    InsertCommand,
    KeyT,
    NoFilter,
    Not,
    OneOf,
    OrderBy,
    Predicate,
    Query,
    ResultT,
    RowT,
    Table,
    UpsertCommand,
    _encode_model,
    validate_query,
)
from umbod.infrastructure.persistence.sqlite.identifiers import validate_sqlite_identifier
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper


class CompiledStatement(BaseModel):
    model_config = ConfigDict(frozen=True)
    statement: str
    parameters: tuple[object, ...] = ()


class SQLiteCompiler:
    def __init__(self, mapper: SQLiteValueMapper) -> None:
        self._mapper = mapper

    def select(
        self, table: Table[RowT, KeyT], query: Query[RowT, ResultT], *, limit_one: bool
    ) -> CompiledStatement:
        self._validate_table(table)
        validate_query(table, query)
        fields = (
            table.row_codec.fields
            if isinstance(query.projection, AllFields)
            else query.projection.fields
        )
        predicate, parameters = self._predicate(query.filter)
        where = "" if predicate == "1" else f" WHERE {predicate}"
        order = ""
        if isinstance(query.ordering, OrderBy):
            order = (
                f" ORDER BY {', '.join(self._quote(field.name) for field in query.ordering.fields)}"
            )
        selected_limit = min(query.limit, 1) if limit_one and query.limit is not None else query.limit
        if limit_one and query.limit is None:
            selected_limit = 1
        limit = "" if selected_limit is None else f" LIMIT {selected_limit}"
        selected = ", ".join(self._quote(field.name) for field in fields)
        return CompiledStatement(
            statement=f"SELECT {selected} FROM {self._quote(table.name)}{where}{order}{limit}",
            parameters=parameters,
        )

    def insert(self, table: Table[RowT, KeyT], command: InsertCommand[RowT]) -> CompiledStatement:
        self._validate_table(table)
        values = _encode_model(table, command.row, table.row_codec.fields)
        fields = {field.name: field for field in table.row_codec.fields}
        columns = tuple(values)
        parameters = tuple(
            self._mapper.bind(fields[name].codec.column_type, values[name]) for name in columns
        )
        return CompiledStatement(
            statement=f"INSERT INTO {self._quote(table.name)} ({', '.join(self._quote(name) for name in columns)}) VALUES ({', '.join('?' for _ in columns)})",
            parameters=parameters,
        )

    def insert_generated_integer_key(
        self,
        table: Table[RowT, KeyT],
        command: GeneratedIntegerKeyInsertCommand[RowT],
    ) -> CompiledStatement:
        self._validate_table(table)
        if command.generated_field not in table.key_codec.fields:
            raise ValueError("Generated field must belong to the table key")
        values = _encode_model(table, command.row, table.row_codec.fields)
        del values[command.generated_field.name]
        fields = {field.name: field for field in table.row_codec.fields}
        columns = tuple(values)
        parameters = tuple(
            self._mapper.bind(fields[name].codec.column_type, values[name]) for name in columns
        )
        return CompiledStatement(
            statement=f"INSERT INTO {self._quote(table.name)} ({', '.join(self._quote(name) for name in columns)}) VALUES ({', '.join('?' for _ in columns)})",
            parameters=parameters,
        )

    def key_exists(
        self, table: Table[RowT, KeyT], values: Mapping[str, object]
    ) -> CompiledStatement:
        self._validate_table(table)
        fields = {field.name: field for field in table.key_codec.fields}
        conditions = " AND ".join(f"{self._quote(name)} = ?" for name in values)
        parameters = tuple(
            self._mapper.bind(fields[name].codec.column_type, value)
            for name, value in values.items()
        )
        return CompiledStatement(
            statement=f"SELECT 1 FROM {self._quote(table.name)} WHERE {conditions} LIMIT 1",
            parameters=parameters,
        )

    def upsert(
        self, table: Table[RowT, KeyT], command: UpsertCommand[RowT, KeyT]
    ) -> CompiledStatement:
        self._validate_table(table)
        keys = _encode_model(table, command.key, table.key_codec.fields)
        values = _encode_model(table, command.row, table.row_codec.fields)
        for name, value in keys.items():
            if values[name] != value:
                raise ValueError(f"Upsert key does not match row field {table.name}.{name}")
        fields = {field.name: field for field in table.row_codec.fields}
        columns = tuple(values)
        updates = tuple(name for name in columns if name not in keys)
        update_sql = ", ".join(
            f"{self._quote(name)} = excluded.{self._quote(name)}" for name in updates
        )
        parameters = tuple(
            self._mapper.bind(fields[name].codec.column_type, values[name]) for name in columns
        )
        conflict_action = f"DO UPDATE SET {update_sql}" if updates else "DO NOTHING"
        statement = f"INSERT INTO {self._quote(table.name)} ({', '.join(self._quote(name) for name in columns)}) VALUES ({', '.join('?' for _ in columns)}) ON CONFLICT({', '.join(self._quote(name) for name in keys)}) {conflict_action}"
        return CompiledStatement(statement=statement, parameters=parameters)

    def delete(self, table: Table[RowT, KeyT], query: DeleteQuery[RowT]) -> CompiledStatement:
        self._validate_table(table)
        validate_query(table, query)
        predicate, parameters = self._predicate(query.filter)
        where = "" if predicate == "1" else f" WHERE {predicate}"
        return CompiledStatement(
            statement=f"DELETE FROM {self._quote(table.name)}{where}", parameters=parameters
        )

    def create_table(self, table: Table[BaseModel, BaseModel]) -> CompiledStatement:
        self._validate_table(table)
        types = {
            ColumnType.TEXT: "TEXT NOT NULL",
            ColumnType.NULLABLE_TEXT: "TEXT",
            ColumnType.INTEGER: "INTEGER NOT NULL",
            ColumnType.BOOLEAN: "INTEGER NOT NULL",
            ColumnType.JSON: "TEXT NOT NULL",
        }
        definitions = tuple(
            f"{self._quote(field.name)} {types[field.codec.column_type]}"
            for field in table.row_codec.fields
        )
        key = ", ".join(self._quote(field.name) for field in table.key_codec.fields)
        return CompiledStatement(
            statement=f"CREATE TABLE IF NOT EXISTS {self._quote(table.name)} ({', '.join(definitions)}, PRIMARY KEY ({key}))"
        )

    def _predicate(self, predicate: Predicate[RowT]) -> tuple[str, tuple[object, ...]]:
        if isinstance(predicate, NoFilter):
            return "1", ()
        if isinstance(predicate, (Equals, GreaterThan)):
            value = predicate.field.codec.encode(predicate.value)
            operator = "=" if isinstance(predicate, Equals) else ">"
            return f"({self._quote(predicate.field.name)} {operator} ?)", (
                self._mapper.bind(predicate.field.codec.column_type, value),
            )
        if isinstance(predicate, OneOf):
            if not predicate.values:
                return "0", ()
            values = tuple(
                self._mapper.bind(
                    predicate.field.codec.column_type, predicate.field.codec.encode(value)
                )
                for value in predicate.values
            )
            return (
                f"({self._quote(predicate.field.name)} IN ({', '.join('?' for _ in values)}))",
                values,
            )
        if isinstance(predicate, Not):
            sql, values = self._predicate(predicate.predicate)
            return f"(NOT ({sql}))", values
        if isinstance(predicate, (AllOf, AnyOf)):
            return self._compound_predicate(predicate)
        raise TypeError(f"Unsupported typed predicate: {type(predicate).__name__}")

    def _compound_predicate(
        self, predicate: AllOf[RowT] | AnyOf[RowT]
    ) -> tuple[str, tuple[object, ...]]:
        if not predicate.predicates:
            return ("1", ()) if isinstance(predicate, AllOf) else ("0", ())
        operator = "AND" if isinstance(predicate, AllOf) else "OR"
        compiled = tuple(self._predicate(item) for item in predicate.predicates)
        statement = f"({' {} '.format(operator).join(f'({item[0]})' for item in compiled)})"
        parameters = tuple(value for item in compiled for value in item[1])
        return statement, parameters

    def _validate_table(self, table: Table[RowT, KeyT]) -> None:
        validate_sqlite_identifier(table.name)
        for field in table.row_codec.fields:
            validate_sqlite_identifier(field.name)

    def _quote(self, identifier: str) -> str:
        validate_sqlite_identifier(identifier)
        return f'"{identifier}"'
