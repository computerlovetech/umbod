from typing import Protocol

from .models import DiscoverPersonalOAuthMetadata, PersonalOAuthMetadataResult


class PersonalOAuthMetadataProvider(Protocol):
    async def discover(self, command: DiscoverPersonalOAuthMetadata) -> PersonalOAuthMetadataResult: ...
