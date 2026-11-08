from typing import Optional

from umbod.core.persistence import (
    AllFields,
    AllOf,
    Database,
    DeleteQuery,
    Equals,
    InsertCommand,
    Query,
    TransactionMode,
    Unordered,
)

from .models import (
    PersonalAccessTokenMetadata,
    StoredPersonalAccessToken,
    TokenOwner,
)
from .schema import (
    PersonalAccessTokenRecord,
    TOKEN_ID,
    TOKEN_ISSUER,
    TOKEN_SUBJECT,
    TOKEN_TABLE,
)


class DatabasePersonalAccessTokenStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def insert(self, record: StoredPersonalAccessToken) -> bool:
        metadata = record.metadata
        row = PersonalAccessTokenRecord(
            token_id=metadata.token_id,
            issuer=metadata.owner.issuer,
            subject=metadata.owner.subject,
            metadata=metadata,
            digest=record.digest,
        )
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            return await session.insert(TOKEN_TABLE, InsertCommand(row=row))

    async def find(self, token_id: str) -> Optional[StoredPersonalAccessToken]:
        async with self._database.read_session() as session:
            row = await session.find_one(
                TOKEN_TABLE, Query(Equals(TOKEN_ID, token_id), AllFields(), Unordered())
            )
        if row is None:
            return None
        return StoredPersonalAccessToken(metadata=row.metadata, digest=row.digest)

    async def list_tokens(
        self, owner: TokenOwner
    ) -> tuple[PersonalAccessTokenMetadata, ...]:
        async with self._database.read_session() as session:
            rows = await session.find_many(
                TOKEN_TABLE,
                Query(
                    AllOf(
                        (
                            Equals(TOKEN_ISSUER, owner.issuer),
                            Equals(TOKEN_SUBJECT, owner.subject),
                        )
                    ),
                    AllFields(),
                    Unordered(),
                ),
            )
        return tuple(
            sorted(
                (row.metadata for row in rows),
                key=lambda item: (item.created_at, item.token_id),
            )
        )

    async def revoke(self, owner: TokenOwner, token_id: str) -> bool:
        async with self._database.session(
            mode=TransactionMode.SERIALIZED_WRITE
        ) as session:
            row = await session.find_one(
                TOKEN_TABLE,
                Query(
                    AllOf(
                        (
                            Equals(TOKEN_ID, token_id),
                            Equals(TOKEN_ISSUER, owner.issuer),
                            Equals(TOKEN_SUBJECT, owner.subject),
                        )
                    ),
                    AllFields(),
                    Unordered(),
                ),
            )
            if row is None:
                return False
            await session.delete(
                TOKEN_TABLE,
                DeleteQuery(
                    AllOf(
                        (
                            Equals(TOKEN_ID, row.token_id),
                            Equals(TOKEN_ISSUER, owner.issuer),
                            Equals(TOKEN_SUBJECT, owner.subject),
                        )
                    )
                ),
            )
            return True
