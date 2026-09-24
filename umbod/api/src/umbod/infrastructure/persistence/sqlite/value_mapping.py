import json

from umbod.core.persistence.query import ColumnType


class SQLiteValueMapper:
    def bind(self, column_type: ColumnType, value: object) -> object:
        if column_type is ColumnType.TEXT:
            if not isinstance(value, str):
                raise TypeError("expected str")
            return value
        if column_type is ColumnType.NULLABLE_TEXT:
            if value is not None and not isinstance(value, str):
                raise TypeError("expected str or None")
            return value
        if column_type is ColumnType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError("expected int")
            return value
        if column_type is ColumnType.BOOLEAN:
            if not isinstance(value, bool):
                raise TypeError("expected bool")
            return int(value)
        if column_type is ColumnType.JSON:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        raise TypeError(f"Unsupported SQLite column type: {column_type}")

    def unbind(self, column_type: ColumnType, value: object) -> object:
        if column_type is ColumnType.TEXT:
            if not isinstance(value, str):
                raise TypeError("expected stored text")
            return value
        if column_type is ColumnType.NULLABLE_TEXT:
            if value is not None and not isinstance(value, str):
                raise TypeError("expected stored text or None")
            return value
        if column_type is ColumnType.INTEGER:
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError("expected stored integer")
            return value
        if column_type is ColumnType.BOOLEAN:
            if value not in (0, 1) or isinstance(value, bool):
                raise ValueError("expected stored boolean integer")
            return bool(value)
        if column_type is ColumnType.JSON:
            if not isinstance(value, str):
                raise TypeError("expected stored JSON text")
            return json.loads(value)
        raise TypeError(f"Unsupported SQLite column type: {column_type}")
