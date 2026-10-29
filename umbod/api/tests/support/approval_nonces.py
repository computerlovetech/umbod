import asyncio

from umbod.core.invocation.approval_nonce_store import ApprovalNonceConsumption


class InMemoryApprovalNonceStore:
    def __init__(self) -> None:
        self._nonces: set[str] = set()
        self._lock = asyncio.Lock()

    async def consume(self, consumption: ApprovalNonceConsumption) -> bool:
        async with self._lock:
            if consumption.nonce in self._nonces:
                return False
            self._nonces.add(consumption.nonce)
            return True
