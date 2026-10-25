from dataclasses import dataclass
from typing import Callable

from umbod.core.filesystem import ContentDriver, NamespaceDriver


@dataclass(frozen=True)
class AdapterPair:
    namespace: NamespaceDriver
    content: ContentDriver


AdapterFactory = Callable[[], AdapterPair]
