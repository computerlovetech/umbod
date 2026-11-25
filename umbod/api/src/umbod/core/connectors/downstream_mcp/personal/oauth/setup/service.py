import asyncio
from collections.abc import Callable
from datetime import datetime

from umbod.core.connectors.downstream_mcp.personal.oauth.diagnostics import PersonalOAuthFailureObserver
from umbod.core.connectors.downstream_mcp.personal.oauth.callback import issuer_callback_uri
from umbod.core.connectors.downstream_mcp.personal.oauth.failures import OAuthFailureEvidence, oauth_failure_evidence
from umbod.core.connectors.downstream_mcp.personal.oauth.authorization import PersonalOAuthProviderUnsupported
from .models import DiscoverPersonalOAuthSetup, ValidatePersonalOAuthSetup, ValidatedPersonalOAuthSetup
from .ports import PersonalOAuthSetupProvider, PersonalOAuthSetupStore
from .state import CompletePersonalOAuthSetup, PersonalOAuthSetupQuery, PersonalOAuthSetupStatus, SetupDiscovered, SetupFailed, SetupScopeMismatch, SetupValidated, StartPersonalOAuthSetup


class PersonalOAuthSetupService:
    def __init__(self, store: PersonalOAuthSetupStore, provider: PersonalOAuthSetupProvider, failures: PersonalOAuthFailureObserver, clock: Callable[[], datetime]) -> None:
        self._store = store
        self._provider = provider
        self._failures = failures
        self._clock = clock

    async def get(self, query: PersonalOAuthSetupQuery) -> PersonalOAuthSetupStatus:
        return await self._store.get(query)

    async def run(self, command: StartPersonalOAuthSetup) -> PersonalOAuthSetupStatus:
        started = await self._store.start(command)
        try:
            async with asyncio.timeout(65):
                if command.operation == "discovery":
                    discovery = await self._provider.discover(DiscoverPersonalOAuthSetup(endpoint_url=started.endpoint_url, redirect_uri=command.redirect_uri, policy=started.policy))
                    state = SetupDiscovered(discovery=discovery, checked_at=self._clock())
                else:
                    result = await self._provider.validate(ValidatePersonalOAuthSetup(endpoint_url=started.endpoint_url, redirect_uri=command.redirect_uri, policy=started.policy))
                    state = SetupValidated(result=result, checked_at=self._clock()) if isinstance(result, ValidatedPersonalOAuthSetup) else SetupScopeMismatch(result=result, checked_at=self._clock())
                    if isinstance(state, SetupScopeMismatch):
                        self._failures.report(command.connector_id, OAuthFailureEvidence(stage="registration", reason="scope_mismatch", downstream_response=state.result.downstream_response))
                discovery = state.discovery if isinstance(state, SetupDiscovered) else state.result.discovery
                if discovery.redirect_uri not in {command.redirect_uri, issuer_callback_uri(command.redirect_uri, discovery.issuer_url)}:
                    raise ValueError("Invalid setup callback binding")
        except Exception as error:
            evidence = oauth_failure_evidence(error, "discovery")
            self._failures.report(command.connector_id, evidence)
            state = SetupFailed(stage=evidence.stage, reason="unsupported" if isinstance(error, PersonalOAuthProviderUnsupported) and evidence.reason == "invalid_response" else evidence.reason, checked_at=self._clock())
        return await self._store.complete(CompletePersonalOAuthSetup(started=started, state=state))
