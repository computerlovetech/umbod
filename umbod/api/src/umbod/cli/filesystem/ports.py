from typing import Protocol

from umbod.core.filesystem import RootBootstrapSpec


class BootstrapPolicySource(Protocol):
    def load(self, policy_file: str) -> RootBootstrapSpec: ...
