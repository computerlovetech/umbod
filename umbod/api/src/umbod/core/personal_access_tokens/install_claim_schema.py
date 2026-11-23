from datetime import datetime, timezone
from typing import ClassVar, cast

from pydantic import BaseModel

from umbod.core.persistence import ColumnCodec, ColumnType, Field, KeyCodec, PydanticJsonCodec, RowCodec, Table, TableIdentity, TextCodec

from .install_claim_ports import InstallClaim, InstallClaimKey
from .models import TokenOwner


class ClaimExpiryCodec(ColumnCodec[datetime]):
    column_type: ClassVar[ColumnType] = ColumnType.TEXT

    def encode(self, value: datetime) -> object:
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")

    def decode(self, value: object) -> datetime:
        return datetime.fromisoformat(TextCodec().decode(value))


CLAIM_IDENTITY = TableIdentity("telemetry_install_claims")
CLAIM_DIGEST = Field[InstallClaim, str](CLAIM_IDENTITY, "digest", TextCodec())
CLAIM_OWNER = Field[InstallClaim, TokenOwner](CLAIM_IDENTITY, "owner", PydanticJsonCodec(TokenOwner))
CLAIM_HARNESS = Field[InstallClaim, str](CLAIM_IDENTITY, "harness", TextCodec())
CLAIM_LOGS_ENDPOINT = Field[InstallClaim, str](CLAIM_IDENTITY, "logs_endpoint", TextCodec())
CLAIM_EXPIRY = Field[InstallClaim, datetime](CLAIM_IDENTITY, "expires_at", ClaimExpiryCodec())
CLAIM_TABLE = Table(
    CLAIM_IDENTITY,
    RowCodec(
        InstallClaim,
        cast(tuple[Field[InstallClaim, object], ...], (CLAIM_DIGEST, CLAIM_OWNER, CLAIM_HARNESS, CLAIM_LOGS_ENDPOINT, CLAIM_EXPIRY)),
    ),
    KeyCodec(InstallClaimKey, cast(tuple[Field[InstallClaim, object], ...], (CLAIM_DIGEST,))),
)
INSTALL_CLAIM_TABLES = cast(tuple[Table[BaseModel, BaseModel], ...], (CLAIM_TABLE,))
