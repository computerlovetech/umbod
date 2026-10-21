from typing import TypeVar

from pydantic import BaseModel

from umbod.core.persistence import AllFields, Predicate, Query, Unordered


RowT = TypeVar("RowT", bound=BaseModel)


def query_all(predicate: Predicate[RowT]) -> Query[RowT, RowT]:
    return Query(filter=predicate, projection=AllFields(), ordering=Unordered())
