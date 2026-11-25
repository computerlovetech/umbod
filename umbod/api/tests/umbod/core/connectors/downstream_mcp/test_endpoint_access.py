import pytest
from pydantic import ValidationError

from umbod.core.connectors.downstream_mcp.endpoint_access import (
    AnonymousAccessRejected,
    AnonymousInitializationResult,
    AnonymousInitializationSucceeded,
    CheckMcpEndpointAccess,
    EndpointAccessInconclusive,
    McpEndpointAccessCheck,
    McpEndpointAccessResult,
    OAuthDiscovered,
    OAuthNotChecked,
    OAuthNotConfirmed,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization.models import (
    PersonalOAuthProviderFailure,
    PersonalOAuthProviderUnsupported,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.metadata import (
    DiscoverPersonalOAuthMetadata,
    PersonalOAuthIssuerSelectionRequired,
    PersonalOAuthMetadataResult,
)
from umbod.core.connectors.downstream_mcp.personal.oauth.metadata.models import (
    AutomaticIssuerSelection,
)

ENDPOINT = "https://mcp.example/remote"


class ScriptedInitialization:
    def __init__(self, result: AnonymousInitializationResult) -> None:
        self._result = result
        self.commands: list[CheckMcpEndpointAccess] = []

    async def initialize(
        self, command: CheckMcpEndpointAccess
    ) -> AnonymousInitializationResult:
        self.commands.append(command)
        return self._result


class ScriptedOAuthMetadata:
    def __init__(
        self,
        result: PersonalOAuthMetadataResult
        | PersonalOAuthProviderFailure
        | PersonalOAuthProviderUnsupported,
    ) -> None:
        self._result = result
        self.commands: list[DiscoverPersonalOAuthMetadata] = []

    async def discover(
        self, command: DiscoverPersonalOAuthMetadata
    ) -> PersonalOAuthMetadataResult:
        self.commands.append(command)
        if isinstance(
            self._result,
            (PersonalOAuthProviderFailure, PersonalOAuthProviderUnsupported),
        ):
            raise self._result
        return self._result


@pytest.mark.parametrize(
    "initialization_result",
    [
        AnonymousInitializationSucceeded(),
        AnonymousAccessRejected(status_code=401),
        AnonymousAccessRejected(status_code=403),
    ],
)
@pytest.mark.asyncio
async def test_check_reports_oauth_evidence_without_overwriting_anonymous_observation(
    initialization_result: AnonymousInitializationResult,
) -> None:
    command = CheckMcpEndpointAccess(endpoint_url=ENDPOINT)
    initialization = ScriptedInitialization(initialization_result)
    metadata = PersonalOAuthIssuerSelectionRequired(
        endpoint_url=ENDPOINT,
        issuer_urls=("https://issuer.example", "https://other-issuer.example"),
    )
    oauth = ScriptedOAuthMetadata(metadata)

    result = await McpEndpointAccessCheck(initialization, oauth).check(command)

    assert result == McpEndpointAccessResult(
        anonymous_initialization=initialization_result,
        oauth=OAuthDiscovered(metadata=metadata),
    )
    assert initialization.commands == [command]
    assert oauth.commands == [
        DiscoverPersonalOAuthMetadata(
            endpoint_url=ENDPOINT,
            issuer_selection=AutomaticIssuerSelection(kind="automatic"),
        )
    ]


@pytest.mark.parametrize(
    "error_type", [PersonalOAuthProviderUnsupported, PersonalOAuthProviderFailure]
)
@pytest.mark.asyncio
async def test_failed_oauth_discovery_does_not_turn_access_rejection_into_oauth_support(
    error_type: type[PersonalOAuthProviderUnsupported]
    | type[PersonalOAuthProviderFailure],
) -> None:
    rejected = AnonymousAccessRejected(status_code=401)
    service = McpEndpointAccessCheck(
        ScriptedInitialization(rejected), ScriptedOAuthMetadata(error_type())
    )

    result = await service.check(CheckMcpEndpointAccess(endpoint_url=ENDPOINT))

    assert result == McpEndpointAccessResult(
        anonymous_initialization=rejected, oauth=OAuthNotConfirmed()
    )


@pytest.mark.asyncio
async def test_successful_anonymous_initialization_does_not_claim_oauth_is_absent() -> (
    None
):
    succeeded = AnonymousInitializationSucceeded()
    service = McpEndpointAccessCheck(
        ScriptedInitialization(succeeded),
        ScriptedOAuthMetadata(PersonalOAuthProviderUnsupported()),
    )

    result = await service.check(CheckMcpEndpointAccess(endpoint_url=ENDPOINT))

    assert result == McpEndpointAccessResult(
        anonymous_initialization=succeeded, oauth=OAuthNotConfirmed()
    )


@pytest.mark.asyncio
async def test_inconclusive_initialization_does_not_trigger_oauth_discovery() -> None:
    inconclusive = EndpointAccessInconclusive(reason="unsafe_destination")
    oauth = ScriptedOAuthMetadata(PersonalOAuthProviderFailure())
    service = McpEndpointAccessCheck(ScriptedInitialization(inconclusive), oauth)

    result = await service.check(CheckMcpEndpointAccess(endpoint_url=ENDPOINT))

    assert result == McpEndpointAccessResult(
        anonymous_initialization=inconclusive, oauth=OAuthNotChecked()
    )
    assert not oauth.commands


@pytest.mark.parametrize(
    "endpoint", ["http://mcp.example/remote", "https://secret@mcp.example/remote"]
)
def test_check_rejects_insecure_or_credential_bearing_url(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        CheckMcpEndpointAccess(endpoint_url=endpoint)
