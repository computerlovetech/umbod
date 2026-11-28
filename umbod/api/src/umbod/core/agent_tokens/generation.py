from datetime import datetime, timezone
from secrets import token_bytes
from uuid import UUID, uuid4


class SystemAgentCredentialClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class SecureAgentCredentialGenerator:
    def generate_id(self) -> UUID:
        return uuid4()

    def generate_secret(self, size: int) -> bytes:
        return token_bytes(size)
