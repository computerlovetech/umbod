def validate_sqlite_identifier(identifier: str) -> None:
    if identifier.lower().startswith("sqlite_"):
        raise ValueError(f"Invalid SQLite persistence identifier: {identifier!r}")
