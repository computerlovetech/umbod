import re

import aiosqlite
from pydantic import BaseModel

from umbod.core.persistence.query import NonReusingIntegerKeyCodec, Table
from umbod.infrastructure.persistence.sqlite.identifiers import validate_sqlite_identifier


_SQL_TOKENS = re.compile(
    r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
    r"`(?:``|[^`])*`|\[[^\]]*\]|(?P<keyword>[A-Za-z_][A-Za-z_0-9$]*)",
    re.DOTALL,
)


async def validate_non_reusing_key_schema(
    connection: aiosqlite.Connection, table: Table[BaseModel, BaseModel]
) -> None:
    if not isinstance(table.key_codec, NonReusingIntegerKeyCodec):
        return
    validate_sqlite_identifier(table.name)
    key_name = table.key_codec.fields[0].name
    validate_sqlite_identifier(key_name)
    async with connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ? COLLATE NOCASE",
        (table.name,),
    ) as cursor:
        definition = await cursor.fetchone()
    async with connection.execute(f'PRAGMA table_info("{table.name}")') as cursor:
        columns = await cursor.fetchall()
    primary_keys = tuple(column for column in columns if column["pk"])
    has_autoincrement = definition is not None and any(
        token.group("keyword") is not None
        and token.group("keyword").upper() == "AUTOINCREMENT"
        for token in _SQL_TOKENS.finditer(definition["sql"] or "")
    )
    if (
        not has_autoincrement
        or len(primary_keys) != 1
        or primary_keys[0]["name"] != key_name
        or primary_keys[0]["type"].upper() != "INTEGER"
    ):
        raise ValueError(
            f"SQLite table {table.name!r} requires INTEGER PRIMARY KEY AUTOINCREMENT "
            f"on {key_name!r}; an explicit migration is required"
        )
