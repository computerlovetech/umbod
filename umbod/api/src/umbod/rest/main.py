from umbod.core.connectors.downstream_mcp.oauth.service import OAuthService
from umbod.rest.connectors.downstream_mcp.oauth import get_oauth_service, router as oauth_router
from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from time import monotonic
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware import Middleware
from starlette.routing import BaseRoute
from umbod.core.connectors.native.registry import ConnectorRegistration
from umbod.core.persistence import PersistenceRuntime
from umbod.core.telemetry.analytics import TelemetryAnalyticsRuntime
from umbod.infrastructure import create_configured_analytics_runtime
from umbod.core.configuration.persistence import AuthenticatedTextCipher
from umbod.core.connectors.downstream_mcp.adapters.settings import downstream_mcp_infrastructure_settings_from_app_config
from umbod.infrastructure import PersonalDiscoveryPreparation
from umbod.rest.authentication import (
    AdminAuthenticationDebugMiddleware,
    AdminAuthenticationMiddleware,
    AdminAuthenticationStrategyFactory,
    AdminAuthorizationServiceFactory,
    JwtVerifierFactory,
)
from umbod.rest.authentication.authorization import JwtVerifier
from umbod.rest.authentication.middleware import SuppliedJwtVerifierFactory
from umbod.rest.authentication.rest_middleware import RestAuthenticationMiddleware
from umbod.rest.admin_overview import router as admin_overview_router
from umbod.rest.user_catalogue import router as user_catalogue_router
from umbod.rest.filesystem import router as filesystem_router
from umbod.rest.filesystem.upload_transfers import router as filesystem_transfer_router
from umbod.rest.filesystem_administration import router as filesystem_administration_router
from umbod.rest.connectors.downstream_mcp.personal_connections import router as personal_connections_router
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback import (
    PersonalOAuthQueryRedactionMiddleware,
)
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback_app import create_personal_oauth_callback_app
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_policy import PersonalOAuthPolicy
from umbod.rest.authentication.csrf_middleware import RestCookieCsrfMiddleware
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
from umbod.rest.groups import router as groups_router
from umbod.rest.identity_directory.routes import admin_router as identity_directory_admin_router, personal_router as identity_directory_personal_router
from umbod.rest.metrics import (
    AdminRestMetricsMiddleware,
    PrometheusRestMetricsRecorder,
    RestMetricsHttpServer,
)
from umbod.config import AppConfig, load_server_app_config
from umbod.logging import create_application_failure_signal, flush_logging
from umbod.rest.settings import APISettings
from umbod.rest.system import router as system_router
from umbod.rest.system.routes import health
from umbod.rest.system.schemas import HealthResponse
from umbod.rest.telemetry_analytics import router as telemetry_analytics_router
from umbod.rest.telemetry.composition import install_analytics_dependencies
from umbod.rest.users import create_user_profile_router
from umbod.rest.users.jwks import (
    CachedSigningKeyResolver,
    DisabledSigningKeyResolver,
    JwksSigningKeySetSource,
)
from umbod.rest.users.signing_keys import SigningKeyResolver


OAuthDependencyOverrides = Mapping[Callable[..., object], Callable[..., object]]


@dataclass(frozen=True)
class _CreateAppArguments:
    settings: APISettings | None
    connector_registrations: Sequence[ConnectorRegistration] | None
    admin_verifier: JwtVerifier | None
    oauth_dependencies: OAuthDependencyOverrides
    user_verifier_factory: JwtVerifierFactory


def _create_oauth_dependency_overrides(service: object) -> OAuthDependencyOverrides:
    if service is None:
        return {}

    def provide_oauth_service() -> OAuthService:
        return cast(OAuthService, service)

    return {get_oauth_service: provide_oauth_service}


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
        oauth_dependencies=_create_oauth_dependency_overrides(kwargs.get("oauth_service")),
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
    app_config: AppConfig,
    verifier_factory: JwtVerifierFactory,
    oauth_dependencies: OAuthDependencyOverrides,
    analytics_runtime: TelemetryAnalyticsRuntime,
) -> tuple[BaseRoute, ...]:
    admin_router = APIRouter()
    admin_router.include_router(connector_router)
    admin_router.include_router(capability_description_router)
    admin_router.include_router(mcp_permission_router)
    admin_router.include_router(groups_router)
    admin_router.include_router(identity_directory_admin_router)
    admin_router.include_router(admin_overview_router)
    admin_router.include_router(telemetry_analytics_router)
    admin_router.include_router(openapi_connector_router)
    admin_router.include_router(oauth_router)
    admin_router.include_router(downstream_mcp_connector_router)
    admin_router.include_router(instance_configuration_router)
    admin_router.include_router(filesystem_administration_router)
    admin_app = SubApiAppFactory(title="umbod-admin-api", router=admin_router).create()
    admin_app.dependency_overrides.update(oauth_dependencies)
    admin_routes = tuple(admin_router.routes)

    def provide_app_config() -> AppConfig:
        return app_config

    _attach_dependency_factories(admin_app, dependency_factories)
    install_analytics_dependencies(admin_app, analytics_runtime)
    admin_app.dependency_overrides[get_app_config] = provide_app_config
    _attach_admin_authorization(admin_app, settings, verifier_factory)
    @admin_app.middleware("http")
    async def prevent_policy_response_caching(
        request: Request, call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        if (
            request.url.path.rstrip("/").endswith("/filesystem/root-access")
            or request.url.path.startswith("/api/admin/telemetry/")
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.mount("/api/admin", admin_app)
    return admin_routes


def _mount_personal_connections_app(
    app: FastAPI,
    settings: APISettings,
    dependency_factories: ConnectorApiDependencyFactories,
) -> None:
    user_router = APIRouter()
    user_router.include_router(create_user_profile_router())
    user_router.include_router(user_catalogue_router)
    user_router.include_router(identity_directory_personal_router)
    user_router.include_router(filesystem_router)
    if settings.personal_connections.enabled:
        user_router.include_router(personal_connections_router)
    personal_app = SubApiAppFactory(
        title="umbod-personal-api", router=user_router
    ).create()
    @personal_app.exception_handler(Exception)
    async def user_internal_error(request: Request, exception: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={"detail": {"code": "internal_server_error", "message": "Request failed."}},
            headers={"Cache-Control": "no-store"},
        )

    _attach_dependency_factories(personal_app, dependency_factories)

    def provide_app_config() -> AppConfig:
        return settings

    personal_app.dependency_overrides[get_app_config] = provide_app_config
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
    callback_app = create_personal_oauth_callback_app(
        dependency_factories, PersonalOAuthPolicy(enabled=True),
    )
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
    analytics_runtime: TelemetryAnalyticsRuntime,
) -> Callable[[FastAPI], AbstractAsyncContextManager[dict[str, SigningKeyResolver]]]:

    return _create_configured_lifespan(metrics_server, persistence_runtime, settings, True, analytics_runtime, True)


def _create_configured_lifespan(
    metrics_server: RestMetricsHttpServer,
    persistence_runtime: PersistenceRuntime,
    settings: APISettings,
    metrics_enabled: bool,
    analytics_runtime: TelemetryAnalyticsRuntime,
    manage_analytics: bool,
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
            if manage_analytics:
                await analytics_runtime.ensure_ready()
            if settings.personal_connections.enabled and settings.personal_connections.oauth_enabled:
                downstream_settings = downstream_mcp_infrastructure_settings_from_app_config(settings)
                await PersonalDiscoveryPreparation(persistence_runtime.database, AuthenticatedTextCipher(downstream_settings.credential_secret)).prepare()
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
            try:
                if manage_analytics:
                    await analytics_runtime.shutdown()
            finally:
                await persistence_runtime.shutdown()

    return lifespan


def create_app(*args: Any, **kwargs: Any) -> FastAPI:
    create_app_arguments = _resolve_create_app_arguments(*args, **kwargs)
    app_settings = create_app_arguments.settings or load_server_app_config(".env")
    return _create_application(
        create_app_arguments, app_settings,
        create_configured_analytics_runtime(app_settings), True, PrometheusRestMetricsRecorder(),
    )


def create_app_with_dependency_factories(
    dependency_factories: ConnectorApiDependencyFactories,
    *args: Any, **kwargs: Any,
) -> FastAPI:
    create_app_arguments = _resolve_create_app_arguments(*args, **kwargs)
    if create_app_arguments.settings is not None or create_app_arguments.connector_registrations is not None:
        raise TypeError("create_app_with_dependency_factories() uses settings and connector registrations from its factories")
    app_settings = dependency_factories.settings
    return _assemble_application(
        create_app_arguments, app_settings,
        create_configured_analytics_runtime(app_settings), True,
        PrometheusRestMetricsRecorder(), dependency_factories,
    )


def create_app_with_analytics_runtime(
    analytics_runtime: TelemetryAnalyticsRuntime, *args: Any, **kwargs: Any,
) -> FastAPI:
    return create_app_with_shared_metrics(
        analytics_runtime, PrometheusRestMetricsRecorder(), *args, **kwargs,
    )


def create_app_with_shared_metrics(
    analytics_runtime: TelemetryAnalyticsRuntime,
    metrics_recorder: PrometheusRestMetricsRecorder,
    *args: Any, **kwargs: Any,
) -> FastAPI:
    create_app_arguments = _resolve_create_app_arguments(*args, **kwargs)
    app_settings = create_app_arguments.settings or load_server_app_config(".env")
    return _create_application(create_app_arguments, app_settings, analytics_runtime, False, metrics_recorder)


def _create_application(
    create_app_arguments: _CreateAppArguments,
    app_settings: APISettings,
    analytics_runtime: TelemetryAnalyticsRuntime,
    manage_analytics: bool,
    metrics_recorder: PrometheusRestMetricsRecorder,
) -> FastAPI:
    app_settings.validate_rest_authentication()
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(
        app_settings.connector_store
    ).create()
    dependency_factories = ConnectorApiDependencyFactories.from_settings(
        app_settings, persistence_runtime, create_app_arguments.connector_registrations
    )
    return _assemble_application(
        create_app_arguments, app_settings, analytics_runtime, manage_analytics,
        metrics_recorder, dependency_factories,
    )


def _assemble_application(
    create_app_arguments: _CreateAppArguments,
    app_settings: APISettings,
    analytics_runtime: TelemetryAnalyticsRuntime,
    manage_analytics: bool,
    metrics_recorder: PrometheusRestMetricsRecorder,
    dependency_factories: ConnectorApiDependencyFactories,
) -> FastAPI:
    app_settings.validate_rest_authentication()
    persistence_runtime = dependency_factories.persistence_runtime
    dependency_factories.validate_startup()
    metrics_server = RestMetricsHttpServer(
        metrics_recorder, app_settings.rest.metrics_port
    )
    app = LifespanRootApiAppFactory(
        app_settings,
        lifespan=_create_configured_lifespan(metrics_server, persistence_runtime, app_settings, app_settings.rest.metrics_enabled, analytics_runtime, manage_analytics),
    ).create()
    verifier_factory = (
        SuppliedJwtVerifierFactory(create_app_arguments.admin_verifier)
        if create_app_arguments.admin_verifier is not None else JwtVerifierFactory()
    )
    admin_routes = _mount_admin_app(
        app, app_settings, dependency_factories, app_settings, verifier_factory,
        create_app_arguments.oauth_dependencies, analytics_runtime,
    )
    _mount_personal_connections_app(
        app, app_settings, dependency_factories
    )
    transfer_app = SubApiAppFactory(title="umbod-filesystem-transfer-api", router=filesystem_transfer_router).create()
    _attach_dependency_factories(transfer_app, dependency_factories)
    app.mount("/api/filesystem", transfer_app)
    _mount_personal_oauth_callback_app(app, app_settings, dependency_factories)
    _mount_system_app(app, dependency_factories)
    app.user_middleware.extend([
        Middleware(
            AdminRestMetricsMiddleware, recorder=metrics_recorder, routes=admin_routes,
            mount_path="/api/admin", application_failures=create_application_failure_signal(),
        ),
        Middleware(
            RestCookieCsrfMiddleware,
            site_base_url=app_settings.endpoints.site_base_url,
            allowed_origins=app_settings.cors.origins,
        ),
        Middleware(
            RestAuthenticationMiddleware,
            settings=app_settings,
            admin_verifier_factory=verifier_factory,
            user_verifier_factory=create_app_arguments.user_verifier_factory,
        ),
    ])
    app.add_middleware(PersonalOAuthQueryRedactionMiddleware)
    return app
