from typing import Protocol

from ..browsing import NodeSummary
from .models import RootBootstrapSpec


class RootProvisioning(Protocol):
    async def provision(self, spec: RootBootstrapSpec) -> NodeSummary: ...
