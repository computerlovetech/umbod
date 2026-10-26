from umbod.core.permissions import InMemoryGroupConnectorToolPermissions


class RuntimeFilesystemGroupClaimFields:
    def __init__(self, state: InMemoryGroupConnectorToolPermissions) -> None:
        self._state = state

    def claim_fields(self) -> tuple[str, ...]:
        return self._state.group_claim_fields


class StaticFilesystemGroupClaimFields:
    def __init__(self, claim: str) -> None:
        self._fields = (claim,)

    def claim_fields(self) -> tuple[str, ...]:
        return self._fields
