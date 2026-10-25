from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.rest.connectors.downstream_mcp.oauth import get_oauth_service, router as oauth_router
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from time import monotonic
from fastapi import APIRouter, FastAPI, Request, Response
from umbod.core.connectors.native.registry import ConnectorRegistration
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.authentication import (
    AdminAuthenticationDebugMiddleware,
    AdminAuthenticationMiddleware,
    AdminAuthenticationStrategyFactory,
    AdminAuthorizationServiceFactory,
    JwtVerifierFactory,
)
from umbod.rest.authentication.authorization import JwtVerifier
from umbod.rest.authentication.middleware import SuppliedJwtVerifierFactory
from umbod.rest.authentication.user_middleware import UserAuthenticationMiddleware
from umbod.core.connectors.downstream_mcp.adapters.settings import personal_identity_policy_from_app_config
from umbod.core.connectors.downstream_mcp.personal_connections.development_identity import local_personal_identity_enabled
from umbod.rest.user_catalogue import router as user_catalogue_router
from umbod.rest.user_catalogue.identity import local_catalogue_identity_enabled
from umbod.rest.connectors.downstream_mcp.personal_connections import router as personal_connections_router
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback import (
    PersonalOAuthQueryRedactionMiddleware,
    callback_response,
    router as personal_oauth_callback_router,
)
from umbod.rest.users.deps import get_access_token_verifier
from umbod.rest.authentication.csrf_middleware import AdminCookieCsrfMiddleware
from umbod.rest.capability_descriptions import router as capability_description_router
from umbod.rest.connectors import (
    downstream_mcp_router as downstream_mcp_connector_router,
    native_router as connector_router,
    openapi_router as openapi_connector_router,
)
from umbod.rest.dependencies import DEPENDENCY_FACTORIES_STATE_KEY
from umbod.rest.factories import (
    ConnectorApiDependencyFactories,
    LifespanRootApiAppFactory,
    SubApiAppFactory,
)
from umbod.rest.instance_configuration import router as instance_configuration_router
from umbod.rest.instance_configuration.dependencies import get_app_config
from umbod.rest.mcp_permissions import router as mcp_permission_router
from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    PrometheusRestMetricsRecorder,
    RestMetricsHttpServer,
    RestMetricsRecorder,
)
from umbod.config import AppConfig, load_server_app_config
from umbod.logging import flush_logging
from umbod.rest.settings import APISettings
from umbod.rest.system import router as system_router
from umbod.rest.system.routes import health
from umbod.rest.system.schemas import HealthResponse
from umbod.rest.telemetry import install_telemetry_receiver
from umbod.rest.users import create_current_user_router
from umbod.rest.users.jwks import (
    CachedSigningKeyResolver,
    DisabledSigningKeyResolver,
    JwksSigningKeySetSource,
)
from umbod.rest.users.signing_keys import SigningKeyResolver


@dataclass(frozen=True)
class _CreateAppArguments:
    settings: APISettings | None
    connector_registrations: Sequence[ConnectorRegistration] | None
    admin_verifier: JwtVerifier | None
    oauth_service: OAuthService | None
    user_verifier_factory: JwtVerifierFactory


def _resolve_create_app_arguments(*args: Any, **kwargs: Any) -> _CreateAppArguments:
    if len(args) > 2:
        raise TypeError("create_app() takes from 0 to 2 positional arguments")
    unknown_keywords = set(kwargs) - {"settings", "connector_registrations", "admin_verifier", "oauth_service", "user_verifier"}
    if unknown_keywords:
        unknown_keyword = next(iter(unknown_keywords))
        raise TypeError(
            f"create_app() got an unexpected keyword argument '{unknown_keyword}'"
        )
    settings = cast(APISettings | None, args[0] if args else kwargs.get("settings"))
    connector_registrations = cast(
        Sequence[ConnectorRegistration] | None,
        args[1] if len(args) > 1 else kwargs.get("connector_registrations"),
    )
    if args and "settings" in kwargs:
        raise TypeError("create_app() got multiple values for argument 'settings'")
    if len(args) > 1 and "connector_registrations" in kwargs:
        raise TypeError(
            "create_app() got multiple values for argument 'connector_registrations'"
        )
    return _CreateAppArguments(
        settings=settings, connector_registrations=connector_registrations,
        admin_verifier=cast(JwtVerifier | None, kwargs.get("admin_verifier")),
        oauth_service=cast(OAuthService | None, kwargs.get("oauth_service")),
        user_verifier_factory=(
            SuppliedJwtVerifierFactory(cast(JwtVerifier, kwargs["user_verifier"]))
            if kwargs.get("user_verifier") is not None else JwtVerifierFactory()
        ),
    )


def _attach_dependency_factories(
    app: FastAPI, dependency_factories: ConnectorApiDependencyFactories
) -> None:

    @app.middleware("http")
    async def attach_dependency_factories(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        setattr(request.state, DEPENDENCY_FACTORIES_STATE_KEY, dependency_factories)
        return await call_next(request)


def _attach_admin_authorization(app: FastAPI, settings: APISettings, verifier_factory: JwtVerifierFactory) -> None:
    if settings.admin_authentication.mode == "disabled":
        return
    app.add_middleware(
        AdminAuthenticationMiddleware,
        strategy=AdminAuthenticationStrategyFactory(
            AdminAuthorizationServiceFactory(verifier_factory)
        ).create(settings),
    )
    if settings.admin_authentication.debug_enabled:
        app.add_middleware(
            AdminAuthenticationDebugMiddleware,
            jwt_header_name=settings.admin_authentication.jwt_header_name,
            profile_header_name=settings.user_profile.jwt_header_name,
        )


def _mount_admin_app(
    app: FastAPI,
    settings: APISettings,
    dependency_factories: ConnectorApiDependencyFactories,
    metrics_recorder: RestMetricsRecorder,
    app_config: AppConfig,
    verifier_factory: JwtVerifierFactory,
    oauth_service: OAuthService | None,
) -> None:
    admin_router = APIRouter()
    admin_router.include_router(create_current_user_router())
    admin_router.include_router(connector_router)
    admin_router.include_router(capability_description_router)
    admin_router.include_router(mcp_permission_router)
    admin_router.include_router(openapi_connector_router)
    admin_router.include_router(oauth_router)
    admin_router.include_router(downstream_mcp_connector_router)
    admin_router.include_router(instance_configuration_router)
    admin_app = SubApiAppFactory(title="umbod-admin-api", router=admin_router).create()
    if oauth_service is not None:
        def provide_oauth_service() -> OAuthService:
            return oauth_service

        admin_app.dependency_overrides[get_oauth_service] = provide_oauth_service
    admin_routes = tuple(admin_router.routes)

    def provide_app_config() -> AppConfig:
        return app_config

    _attach_dependency_factories(admin_app, dependency_factories)
    admin_app.dependency_overrides[get_app_config] = provide_app_config
    def provide_access_token_verifier() -> JwtVerifier:
        return verifier_factory.create(settings)

    admin_app.dependency_overrides[get_access_token_verifier] = provide_access_token_verifier
    _attach_admin_authorization(admin_app, settings, verifier_factory)
    admin_app.add_middleware(
        AdminCookieCsrfMiddleware,
        site_base_url=settings.endpoints.site_base_url,
        allowed_origins=settings.cors.origins,
    )
    admin_app.add_middleware(
        AdminRestMetricsMiddleware, recorder=metrics_recorder, routes=admin_routes
    )
    app.mount("/api/admin", admin_app)


def _mount_personal_connections_app(
    app: FastAPI,
    settings: APISettings,
    dependency_factories: ConnectorApiDependencyFactories,
    verifier_factory: JwtVerifierFactory,
) -> None:
    user_router = APIRouter()
    user_router.include_router(user_catalogue_router)
    if settings.personal_connections.enabled:
        user_router.include_router(personal_connections_router)
    personal_app = SubApiAppFactory(
        title="umbod-personal-api", router=user_router
    ).create()
    _attach_dependency_factories(personal_app, dependency_factories)
    personal_app.add_middleware(
        UserAuthenticationMiddleware,
        verifier=verifier_factory.create(settings),
        jwt_header_name=settings.admin_authentication.jwt_header_name,
        allow_missing_simulated_token=(
            type(verifier_factory) is JwtVerifierFactory
            and (
                local_personal_identity_enabled(personal_identity_policy_from_app_config(settings))
                if settings.personal_connections.enabled
                else local_catalogue_identity_enabled(settings)
            )
        ),
    )
    personal_app.add_middleware(
        AdminCookieCsrfMiddleware,
        site_base_url=settings.endpoints.site_base_url,
        allowed_origins=settings.cors.origins,
    )
    @personal_app.middleware("http")
    async def prevent_user_response_caching(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/api/me", personal_app)


def _mount_personal_oauth_callback_app(
    app: FastAPI,
    settings: APISettings,
    dependency_factories: ConnectorApiDependencyFactories,
) -> None:
    if not (settings.personal_connections.enabled and settings.personal_connections.oauth_enabled):
        return
    callback_app = FastAPI(
        title="umbod-personal-oauth-callback", docs_url=None, redoc_url=None,
        openapi_url=None, redirect_slashes=False,
    )
    callback_app.include_router(personal_oauth_callback_router)
    _attach_dependency_factories(callback_app, dependency_factories)

    @callback_app.middleware("http")
    async def protect_callback_response(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            return callback_response(400)
        if response.status_code != 200:
            return callback_response(400)
        return response

    app.mount("/api/oauth/downstream-mcp", callback_app)


def _mount_system_app(
    app: FastAPI, dependency_factories: ConnectorApiDependencyFactories
) -> None:
    system_app = SubApiAppFactory(
        title="umbod-system-api", router=system_router
    ).create()
    _attach_dependency_factories(system_app, dependency_factories)
    app.mount("/system", system_app)
    app.add_api_route(
        "/api/system/health", health, response_model=HealthResponse, methods=["GET"]
    )


def _create_lifespan(
    metrics_server: RestMetricsHttpServer,
    persistence_runtime: PersistenceRuntime,
    settings: APISettings,
) -> Callable[[FastAPI], AbstractAsyncContextManager[dict[str, SigningKeyResolver]]]:

    return _create_configured_lifespan(metrics_server, persistence_runtime, settings, True)


def _create_configured_lifespan(
    metrics_server: RestMetricsHttpServer,
    persistence_runtime: PersistenceRuntime,
    settings: APISettings,
    metrics_enabled: bool,
) -> Callable[[FastAPI], AbstractAsyncContextManager[dict[str, SigningKeyResolver]]]:

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[dict[str, SigningKeyResolver]]:
        resolver = (
            CachedSigningKeyResolver(
                JwksSigningKeySetSource(
                    settings.admin_authentication.jwks_url, timeout_seconds=3.0
                ),
                monotonic,
                ttl_seconds=300.0,
                refresh_cooldown_seconds=5.0,
            )
            if settings.user_profile.mode == "id_token"
            else DisabledSigningKeyResolver()
        )
        try:
            await persistence_runtime.readiness.ensure_ready()
            try:
                if metrics_enabled:
                    await metrics_server.start()
            except BaseException:
                if metrics_enabled:
                    await metrics_server.stop()
                raise
            try:
                yield {"profile_signing_key_resolver": resolver}
            finally:
                if metrics_enabled:
                    await metrics_server.stop()
                flush_logging()
        finally:
            resolver.clear()
            await persistence_runtime.shutdown()

    return lifespan


def create_app(*args: Any, **kwargs: Any) -> FastAPI:
    create_app_arguments = _resolve_create_app_arguments(*args, **kwargs)
    app_settings = create_app_arguments.settings or load_server_app_config(".env")
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(
        app_settings.connector_store
    ).create()
    dependency_factories = ConnectorApiDependencyFactories.from_settings(
        app_settings, persistence_runtime, create_app_arguments.connector_registrations
    )
    dependency_factories.validate_startup()
    metrics_recorder = PrometheusRestMetricsRecorder()
    metrics_server = RestMetricsHttpServer(
        metrics_recorder, app_settings.rest.metrics_port
    )
    app = LifespanRootApiAppFactory(
        app_settings,
        lifespan=_create_configured_lifespan(metrics_server, persistence_runtime, app_settings, app_settings.rest.metrics_enabled),
    ).create()
    verifier_factory = (
        SuppliedJwtVerifierFactory(create_app_arguments.admin_verifier)
        if create_app_arguments.admin_verifier is not None else JwtVerifierFactory()
    )
    _mount_admin_app(
        app, app_settings, dependency_factories, metrics_recorder, app_settings, verifier_factory,
        create_app_arguments.oauth_service,
    )
    _mount_personal_connections_app(
        app, app_settings, dependency_factories, create_app_arguments.user_verifier_factory
    )
    _mount_personal_oauth_callback_app(app, app_settings, dependency_factories)
    _mount_system_app(app, dependency_factories)
    install_telemetry_receiver(app, app_settings)
    app.add_middleware(PersonalOAuthQueryRedactionMiddleware)
    return app
