from fastapi import FastAPI
from starlette.routing import Mount

from umbod.config import AppConfig
from umbod.rest.authentication.authorization import JwtVerifier
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback_app import create_personal_oauth_callback_app
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_policy import PersonalOAuthPolicy, get_personal_oauth_policy
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.main import create_app_with_dependency_factories
from tests.persistence_runtime import create_inmemory_runtime


def create_personal_oauth_business_app(settings: AppConfig, user_verifier: JwtVerifier) -> FastAPI:
    runtime = create_inmemory_runtime()
    factories = ConnectorApiDependencyFactories.from_settings(settings, runtime, [])
    return create_personal_oauth_app(factories, user_verifier)


def create_personal_oauth_app(factories: ConnectorApiDependencyFactories, user_verifier: JwtVerifier) -> FastAPI:
    app = create_app_with_dependency_factories(factories, user_verifier=user_verifier)
    policy = PersonalOAuthPolicy(enabled=True)

    def provide_policy() -> PersonalOAuthPolicy:
        return policy

    personal_app = next(route.app for route in app.routes if isinstance(route, Mount) and route.path == "/api/me")
    personal_app.dependency_overrides[get_personal_oauth_policy] = provide_policy
    app.mount("/api/oauth/downstream-mcp", create_personal_oauth_callback_app(factories, policy))
    return app
