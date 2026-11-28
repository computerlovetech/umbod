from typing import TypeVar

from umbod.proxies import PydanticModel
from umbod.core.persistence import AllFields, Predicate, Query, Unordered


RowT = TypeVar("RowT", bound=PydanticModel)


def query_all(predicate: Predicate[RowT]) -> Query[RowT, RowT]:
    return Query(filter=predicate, projection=AllFields(), ordering=Unordered())
