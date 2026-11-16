from umbod.core.connectors.downstream_mcp.personal_oauth_metadata import DiscoverPersonalOAuthMetadata, PersonalOAuthMetadataResult


class InMemoryPersonalOAuthMetadataProvider:
    def __init__(self, result: PersonalOAuthMetadataResult) -> None:
        self.result = result
        self.commands: list[DiscoverPersonalOAuthMetadata] = []

    async def discover(self, command: DiscoverPersonalOAuthMetadata) -> PersonalOAuthMetadataResult:
        self.commands.append(command)
        return self.result
