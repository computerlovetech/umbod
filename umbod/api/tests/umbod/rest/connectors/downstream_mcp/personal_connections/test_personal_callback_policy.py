from collections.abc import AsyncIterator
from contextlib import aclosing, asynccontextmanager
from unittest.mock import Mock

import pytest

from umbod.config.app import AppConfig
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.callback import CallbackURLPolicy
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_dependencies import get_personal_callback_policy
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.connectors.downstream_mcp.personal_connections import oauth_dependencies, refresh_dependencies
from umbod.core.connectors.downstream_mcp.personal_connections.oauth_ports import PersonalOAuthProvider
from umbod.core.connectors.downstream_mcp.personal_connections.refresh_provider_ports import PersonalOAuthRefreshProvider


@pytest.fixture
def callback_settings() -> AppConfig:
    return AppConfig(
        runtime={"profile": "local", "auth": "dev"},
        admin_authentication={"mode": "simulation", "environment": "development", "simulated_user_id": "test-user"},
        personal_connections={"enabled": True, "identity_namespace": "test:callbacks"},
    )


def test_only_explicit_local_simulation_settings_select_http_callback_policy(callback_settings: AppConfig) -> None:
    factories = Mock(spec=ConnectorApiDependencyFactories, settings=callback_settings)
    assert get_personal_callback_policy(factories) is CallbackURLPolicy.LOCAL_DEVELOPMENT


@pytest.mark.parametrize("section,updates", (
    ("runtime", {"profile": "production"}),
    ("runtime", {"auth": "google"}),
    ("runtime", {"auth": "azure"}),
    ("runtime", {"auth": "auth0"}),
    ("runtime", {"auth": "none"}),
    ("admin_authentication", {"mode": "jwt"}),
    ("admin_authentication", {"mode": "disabled"}),
    ("admin_authentication", {"environment": "production"}),
    ("admin_authentication", {"simulated_user_id": " "}),
    ("personal_connections", {"enabled": False}),
    ("personal_connections", {"identity_namespace": ""}),
    ("personal_connections", {"identity_namespace": "test:"}),
    ("personal_connections", {"identity_namespace": "test: "}),
    ("personal_connections", {"identity_namespace": " test:callbacks"}),
    ("personal_connections", {"identity_namespace": "test:callbacks "}),
    ("personal_connections", {"identity_namespace": "issuer:real"}),
))
def test_ineligible_trusted_settings_select_strict_callback_policy(
    callback_settings: AppConfig, section: str, updates: dict[str, object],
) -> None:
    settings = callback_settings.model_copy(update={section: getattr(callback_settings, section).model_copy(update=updates)})
    factories = Mock(spec=ConnectorApiDependencyFactories, settings=settings)
    assert get_personal_callback_policy(factories) is CallbackURLPolicy.STRICT


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", tuple(CallbackURLPolicy))
async def test_authorization_dependency_passes_trusted_policy_to_provider_factory(
    monkeypatch: pytest.MonkeyPatch, policy: CallbackURLPolicy,
) -> None:
    captured: list[CallbackURLPolicy] = []
    provider: PersonalOAuthProvider = Mock(spec=PersonalOAuthProvider)

    @asynccontextmanager
    async def configured(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthProvider]:
        captured.append(callback_policy)
        yield provider

    monkeypatch.setattr(oauth_dependencies, "configured_personal_oauth_provider", configured)
    async with aclosing(oauth_dependencies.get_personal_oauth_provider(callback_policy=policy, enabled=None)) as generated:
        assert await anext(generated) is provider
    assert captured == [policy]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", tuple(CallbackURLPolicy))
async def test_refresh_dependency_passes_trusted_policy_to_provider_factory(
    monkeypatch: pytest.MonkeyPatch, policy: CallbackURLPolicy,
) -> None:
    captured: list[CallbackURLPolicy] = []
    provider: PersonalOAuthRefreshProvider = Mock(spec=PersonalOAuthRefreshProvider)

    @asynccontextmanager
    async def configured(callback_policy: CallbackURLPolicy) -> AsyncIterator[PersonalOAuthRefreshProvider]:
        captured.append(callback_policy)
        yield provider

    monkeypatch.setattr(refresh_dependencies, "configured_personal_oauth_refresh_provider", configured)
    async with aclosing(refresh_dependencies.get_personal_refresh_provider(callback_policy=policy, enabled=None)) as generated:
        assert await anext(generated) is provider
    assert captured == [policy]
