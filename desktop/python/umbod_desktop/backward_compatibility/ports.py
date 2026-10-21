from typing import Protocol

from .contracts import LegacyAuthorization, PrefixUpdate


class PrefixRepair(Protocol):
    async def update_prefix(self, update: PrefixUpdate) -> None: ...


class LegacyAuthorizationImporter(Protocol):
    def import_authorization(self, authorization: LegacyAuthorization) -> None: ...
