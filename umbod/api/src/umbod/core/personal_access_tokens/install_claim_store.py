from datetime import datetime

from umbod.core.harness_plugins import Harness
from umbod.core.persistence import AllFields, Database, DeleteQuery, Equals, GreaterThan, InsertCommand, Not, Query, TransactionMode, Unordered

from .errors import PersonalAccessTokenCollision
from .install_claim_ports import BuildInstallToken, InstallClaim, InstallClaimKey, InvalidInstallClaim
from .install_claim_schema import CLAIM_DIGEST, CLAIM_EXPIRY, CLAIM_TABLE
from .models import IssuedPersonalAccessToken
from .store import insert_token_record


class DatabaseInstallClaimStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(self, claim: InstallClaim, now: datetime) -> None:
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            await session.delete(CLAIM_TABLE, DeleteQuery(Not(GreaterThan(CLAIM_EXPIRY, now))))
            if not await session.insert(CLAIM_TABLE, InsertCommand(row=claim)):
                raise RuntimeError("Install claim collision")

    async def redeem(
        self, key: InstallClaimKey, harness: Harness, build_token: BuildInstallToken,
    ) -> IssuedPersonalAccessToken:
        predicate = Equals(CLAIM_DIGEST, key.digest)
        async with self._database.session(mode=TransactionMode.SERIALIZED_WRITE) as session:
            claim = await session.find_one(CLAIM_TABLE, Query(predicate, AllFields(), Unordered()))
            if claim is None or claim.harness != harness:
                raise InvalidInstallClaim()
            stored, issued = build_token(claim)
            if await session.delete(CLAIM_TABLE, DeleteQuery(predicate)) != 1:
                raise InvalidInstallClaim()
            if not await insert_token_record(session, stored):
                raise PersonalAccessTokenCollision()
        return issued
