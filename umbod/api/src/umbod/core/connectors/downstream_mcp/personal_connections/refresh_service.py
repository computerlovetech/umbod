import asyncio
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from .inventory_models import PersonalConnectorQuery, VerifiedGroupMembership
from .inventory_ports import PersonalConnectorInventory
from .models import MissingCanonicalPrincipal, PersonalConnectionKey
from .ports import CanonicalPrincipalProvider
from .refresh_models import CompletePersonalRefresh, FailPersonalRefresh, PersonalRefreshCommand, PersonalRefreshUnavailable, ReservePersonalRefresh
from .refresh_ports import PersonalRefreshStore
from .refresh_provider_models import PersonalOAuthRefreshDenied, RefreshPersonalOAuth
from .refresh_provider_ports import PersonalOAuthRefreshProvider


class PersonalRefreshService:
    def __init__(self, principal: CanonicalPrincipalProvider, groups: VerifiedGroupMembership, inventory: PersonalConnectorInventory, store: PersonalRefreshStore, provider: PersonalOAuthRefreshProvider, clock: Callable[[], datetime]) -> None:
        self._principal = principal
        self._groups = groups
        self._inventory = inventory
        self._store = store
        self._provider = provider
        self._clock = clock

    async def refresh(self, connector_id: str) -> None:
        owner = await self._principal.get_principal()
        if owner is None:
            raise MissingCanonicalPrincipal()
        await self._inventory.get(PersonalConnectorQuery(connector_id=connector_id))
        key = PersonalConnectionKey(principal=owner, connector_id=connector_id)
        claim_id = uuid4().hex
        claim = await self._store.reserve(ReservePersonalRefresh(key=key, group_ids=self._groups.group_ids, claim_id=claim_id, now=self._clock()))
        try:
            now = self._clock()
            preparation = RefreshPersonalOAuth(grant=claim.grant, policy=claim.policy, now=now, timeout_seconds=min(20, (claim.deadline - now).total_seconds()))
            claim = await self._store.exchange(PersonalRefreshCommand(key=key, claim_id=claim_id, now=self._clock()))
        except BaseException:
            await asyncio.shield(asyncio.wait_for(self._store.release(PersonalRefreshCommand(key=key, claim_id=claim_id, now=self._clock())), timeout=2))
            raise
        try:
            remaining = min(preparation.timeout_seconds, (claim.deadline - self._clock()).total_seconds())
            if remaining <= 0:
                raise TimeoutError()
            command = RefreshPersonalOAuth(grant=claim.grant, policy=claim.policy, now=self._clock(), timeout_seconds=remaining)
            async with asyncio.timeout(remaining):
                authorization = await self._provider.refresh(command)
            await self._store.complete(CompletePersonalRefresh(key=key, claim_id=claim_id, now=self._clock(), authorization=authorization))
        except BaseException as error:
            reason = "refresh_denied" if isinstance(error, PersonalOAuthRefreshDenied) else "refresh_uncertain"
            try:
                await asyncio.shield(asyncio.wait_for(self._store.fail(FailPersonalRefresh(key=key, claim_id=claim_id, now=self._clock(), reason=reason)), timeout=2))
            except Exception:
                pass
            if not isinstance(error, Exception):
                raise
            if isinstance(error, PersonalOAuthRefreshDenied):
                from .refresh_models import PersonalRefreshReconnectRequired

                raise PersonalRefreshReconnectRequired() from None
            raise PersonalRefreshUnavailable() from None
