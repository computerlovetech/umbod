from umbod.infrastructure.persistence.sqlite.compiler import SQLiteCompiler
from umbod.infrastructure.persistence.sqlite.value_mapping import SQLiteValueMapper
from typing import cast
import pytest
from pydantic import BaseModel, ConfigDict
from umbod.core.persistence import Field, KeyCodec, RowCodec, Table, TableIdentity, TextCodec

class ReservedRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str

class ReservedKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    record_id: str

def _table(table_name: str, field_name: str='record_id') -> Table[ReservedRow, ReservedKey]:
    identity = TableIdentity(table_name)
    field = Field[ReservedRow, str](identity, field_name, TextCodec())
    fields = cast(tuple[Field[ReservedRow, object], ...], (field,))
    return Table(identity, RowCodec(ReservedRow, fields), KeyCodec(ReservedKey, fields))

def test_sqlite_compiler_rejects_reserved_table_identifier_at_adapter_boundary() -> None:
    compiler = SQLiteCompiler(SQLiteValueMapper())
    with pytest.raises(ValueError, match='Invalid SQLite persistence identifier'):
        compiler.create_table(cast(Table[BaseModel, BaseModel], _table('sqlite_internal')))

def test_sqlite_compiler_rejects_reserved_field_identifier_at_adapter_boundary() -> None:
    compiler = SQLiteCompiler(SQLiteValueMapper())
    with pytest.raises(ValueError, match='Invalid SQLite persistence identifier'):
        compiler.create_table(cast(Table[BaseModel, BaseModel], _table('portable_table', 'sqlite_internal')))
