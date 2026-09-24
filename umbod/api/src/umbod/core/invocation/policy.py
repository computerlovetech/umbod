from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Protocol


ConnectorKind = Literal["native", "openapi", "downstream_mcp"]
InvocationPolicyMode = Literal["direct", "ask"]


@dataclass(frozen=True)
class ConnectorInvocation:
    connector_kind: ConnectorKind
    connector_id: str
    operation_name: str
    public_tool_name: str
    arguments: Mapping[str, Any]

    @classmethod
    def create(
        cls,
        *,
        connector_kind: ConnectorKind,
        connector_id: str,
        operation_name: str,
        public_tool_name: str,
        arguments: Mapping[str, Any],
    ) -> "ConnectorInvocation":
        return cls(
            connector_kind=connector_kind,
            connector_id=connector_id,
            operation_name=operation_name,
            public_tool_name=public_tool_name,
            arguments=MappingProxyType(deepcopy(dict(arguments))),
        )


@dataclass(frozen=True)
class ConnectorInvocationPolicyKey:
    connector_kind: ConnectorKind
    connector_id: str
    operation_name: str


@dataclass(frozen=True)
class ConnectorInvocationPolicyRecord:
    key: ConnectorInvocationPolicyKey
    mode: InvocationPolicyMode
    revision: int


@dataclass(frozen=True)
class ConnectorInvocationPolicyUpdate:
    key: ConnectorInvocationPolicyKey
    mode: InvocationPolicyMode
    expected_revision: int


@dataclass(frozen=True)
class ConnectorInvocationPolicyConflict:
    key: ConnectorInvocationPolicyKey
    expected_revision: int
    current_mode: InvocationPolicyMode
    current_revision: int


class ConnectorInvocationPolicyRevisionConflict(Exception):
    def __init__(self, conflicts: tuple[ConnectorInvocationPolicyConflict, ...]) -> None:
        super().__init__("Connector invocation policy revision conflict")
        self.conflicts = conflicts


@dataclass(frozen=True)
class DirectInvocationDecision:
    mode: Literal["direct"] = "direct"


@dataclass(frozen=True)
class AskInvocationDecision:
    policy_revision: int
    mode: Literal["ask"] = "ask"


ConnectorInvocationDecision = DirectInvocationDecision | AskInvocationDecision
DIRECT_INVOCATION = DirectInvocationDecision()


class ConnectorInvocationPolicyStore(Protocol):
    async def get(
        self, key: ConnectorInvocationPolicyKey
    ) -> ConnectorInvocationPolicyRecord | None: ...

    async def list(
        self, keys: tuple[ConnectorInvocationPolicyKey, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord | None, ...]: ...

    async def delete_connector(self, connector_kind: ConnectorKind, connector_id: str) -> None: ...

    async def compare_and_set_batch(
        self, updates: tuple[ConnectorInvocationPolicyUpdate, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord, ...]: ...


class InMemoryConnectorInvocationPolicyStore:
    def __init__(self) -> None:
        self._records: dict[ConnectorInvocationPolicyKey, ConnectorInvocationPolicyRecord] = {}

    async def get(
        self, key: ConnectorInvocationPolicyKey
    ) -> ConnectorInvocationPolicyRecord | None:
        return self._records.get(key)

    async def list(
        self, keys: tuple[ConnectorInvocationPolicyKey, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord | None, ...]:
        return tuple(self._records.get(key) for key in keys)

    async def delete_connector(self, connector_kind: ConnectorKind, connector_id: str) -> None:
        self._records = {
            key: record
            for key, record in self._records.items()
            if key.connector_kind != connector_kind or key.connector_id != connector_id
        }

    async def compare_and_set_batch(
        self, updates: tuple[ConnectorInvocationPolicyUpdate, ...]
    ) -> tuple[ConnectorInvocationPolicyRecord, ...]:
        conflicts = tuple(
            ConnectorInvocationPolicyConflict(
                key=update.key,
                expected_revision=update.expected_revision,
                current_mode=self._records.get(update.key).mode
                if update.key in self._records
                else "direct",
                current_revision=self._records.get(update.key).revision
                if update.key in self._records
                else 0,
            )
            for update in updates
            if update.expected_revision
            != (self._records.get(update.key).revision if update.key in self._records else 0)
        )
        if conflicts:
            raise ConnectorInvocationPolicyRevisionConflict(conflicts)
        results: list[ConnectorInvocationPolicyRecord] = []
        for update in updates:
            current = self._records.get(update.key)
            if current is not None and current.mode == update.mode:
                results.append(current)
                continue
            if current is None and update.mode == "direct":
                results.append(
                    ConnectorInvocationPolicyRecord(key=update.key, mode="direct", revision=0)
                )
                continue
            record = ConnectorInvocationPolicyRecord(
                key=update.key,
                mode=update.mode,
                revision=update.expected_revision + 1,
            )
            self._records[update.key] = record
            results.append(record)
        return tuple(results)


class ConnectorInvocationDenied(Exception):
    pass


class ConnectorInvocationApprovalRequired(ConnectorInvocationDenied):
    def __init__(self, invocation: ConnectorInvocation, policy_revision: int) -> None:
        super().__init__("Connector invocation approval required")
        self.invocation = invocation
        self.policy_revision = policy_revision


async def evaluate_direct_invocation(
    policy: "ConnectorInvocationPolicy", invocation: ConnectorInvocation
) -> None:
    decision = await policy.evaluate(invocation)
    if isinstance(decision, AskInvocationDecision):
        raise ConnectorInvocationApprovalRequired(invocation, decision.policy_revision)


class ConnectorInvocationPolicy(Protocol):
    async def evaluate(self, invocation: ConnectorInvocation) -> ConnectorInvocationDecision: ...


class StoredConnectorInvocationPolicy:
    def __init__(self, store: ConnectorInvocationPolicyStore) -> None:
        self._store = store

    async def evaluate(self, invocation: ConnectorInvocation) -> ConnectorInvocationDecision:
        key = ConnectorInvocationPolicyKey(
            connector_kind=invocation.connector_kind,
            connector_id=invocation.connector_id,
            operation_name=invocation.operation_name,
        )
        record = await self._store.get(key)
        if record is None or record.mode == "direct":
            return DIRECT_INVOCATION
        return AskInvocationDecision(policy_revision=record.revision)


class PermitAllConnectorInvocationPolicy:
    async def evaluate(self, invocation: ConnectorInvocation) -> ConnectorInvocationDecision:
        return DIRECT_INVOCATION


__all__ = [
    "AskInvocationDecision",
    "ConnectorInvocation",
    "ConnectorInvocationApprovalRequired",
    "ConnectorInvocationDecision",
    "ConnectorInvocationDenied",
    "ConnectorInvocationPolicy",
    "ConnectorInvocationPolicyKey",
    "ConnectorInvocationPolicyConflict",
    "ConnectorInvocationPolicyRecord",
    "ConnectorInvocationPolicyRevisionConflict",
    "ConnectorInvocationPolicyStore",
    "ConnectorInvocationPolicyUpdate",
    "ConnectorKind",
    "DIRECT_INVOCATION",
    "DirectInvocationDecision",
    "InMemoryConnectorInvocationPolicyStore",
    "InvocationPolicyMode",
    "PermitAllConnectorInvocationPolicy",
    "StoredConnectorInvocationPolicy",
    "evaluate_direct_invocation",
]
