from umbod.infrastructure import ConfiguredPersistenceRuntimeProvider
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any, cast
from fastapi import APIRouter, FastAPI, Request, Response
from umbod.core.connectors.native.registry import ConnectorRegistration
from umbod.core.persistence import PersistenceRuntime
from umbod.rest.authentication import AdminAuthenticationDebugMiddleware, AdminAuthenticationMiddleware, AdminAuthenticationStrategyFactory, AdminAuthorizationServiceFactory, JwtVerifierFactory
from umbod.rest.capability_descriptions import router as capability_description_router
from umbod.rest.connectors import (
    downstream_mcp_router as downstream_mcp_connector_router,
    native_router as connector_router,
    openapi_router as openapi_connector_router,
)
from umbod.rest.dependencies import DEPENDENCY_FACTORIES_STATE_KEY
from umbod.rest.factories import ConnectorApiDependencyFactories, LifespanRootApiAppFactory, SubApiAppFactory
from umbod.rest.instance_configuration import router as instance_configuration_router
from umbod.rest.instance_configuration.dependencies import get_app_config
from umbod.rest.mcp_permissions import router as mcp_permission_router
from umbod.rest.metrics import AdminRestMetricsMiddleware, PrometheusRestMetricsRecorder, RestMetricsHttpServer, RestMetricsRecorder
from umbod.config import AppConfig, load_app_config
from umbod.logging import flush_logging
from umbod.rest.settings import APISettings
from umbod.rest.system import router as system_router
from umbod.rest.users import create_current_user_router

@dataclass(frozen=True)
class _CreateAppArguments:
    settings: APISettings | None
    connector_registrations: Sequence[ConnectorRegistration] | None

def _resolve_create_app_arguments(*args: Any, **kwargs: Any) -> _CreateAppArguments:
    if len(args) > 2:
        raise TypeError('create_app() takes from 0 to 2 positional arguments')
    unknown_keywords = set(kwargs) - {'settings', 'connector_registrations'}
    if unknown_keywords:
        unknown_keyword = next(iter(unknown_keywords))
        raise TypeError(f"create_app() got an unexpected keyword argument '{unknown_keyword}'")
    settings = cast(APISettings | None, args[0] if args else kwargs.get('settings'))
    connector_registrations = cast(Sequence[ConnectorRegistration] | None, args[1] if len(args) > 1 else kwargs.get('connector_registrations'))
    if args and 'settings' in kwargs:
        raise TypeError("create_app() got multiple values for argument 'settings'")
    if len(args) > 1 and 'connector_registrations' in kwargs:
        raise TypeError("create_app() got multiple values for argument 'connector_registrations'")
    return _CreateAppArguments(settings=settings, connector_registrations=connector_registrations)

def _attach_dependency_factories(app: FastAPI, dependency_factories: ConnectorApiDependencyFactories) -> None:

    @app.middleware('http')
    async def attach_dependency_factories(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        setattr(request.state, DEPENDENCY_FACTORIES_STATE_KEY, dependency_factories)
        return await call_next(request)

def _attach_admin_authorization(app: FastAPI, settings: APISettings) -> None:
    if settings.admin_authentication.mode == 'disabled':
        return
    app.add_middleware(AdminAuthenticationMiddleware, strategy=AdminAuthenticationStrategyFactory(AdminAuthorizationServiceFactory(JwtVerifierFactory())).create(settings))
    if settings.admin_authentication.debug_enabled:
        app.add_middleware(AdminAuthenticationDebugMiddleware, jwt_header_name=settings.admin_authentication.jwt_header_name)

def _mount_admin_app(app: FastAPI, settings: APISettings, dependency_factories: ConnectorApiDependencyFactories, metrics_recorder: RestMetricsRecorder, app_config: AppConfig) -> None:
    admin_router = APIRouter()
    admin_router.include_router(create_current_user_router(settings))
    admin_router.include_router(connector_router)
    admin_router.include_router(capability_description_router)
    admin_router.include_router(mcp_permission_router)
    admin_router.include_router(openapi_connector_router)
    admin_router.include_router(downstream_mcp_connector_router)
    admin_router.include_router(instance_configuration_router)
    admin_app = SubApiAppFactory(title='umbod-admin-api', router=admin_router).create()
    admin_routes = tuple(admin_router.routes)

    def provide_app_config() -> AppConfig:
        return app_config
    _attach_dependency_factories(admin_app, dependency_factories)
    admin_app.dependency_overrides[get_app_config] = provide_app_config
    _attach_admin_authorization(admin_app, settings)
    admin_app.add_middleware(AdminRestMetricsMiddleware, recorder=metrics_recorder, routes=admin_routes)
    app.mount('/admin', admin_app)

def _mount_system_app(app: FastAPI, dependency_factories: ConnectorApiDependencyFactories) -> None:
    system_app = SubApiAppFactory(title='umbod-system-api', router=system_router).create()
    _attach_dependency_factories(system_app, dependency_factories)
    app.mount('/system', system_app)

def _create_lifespan(metrics_server: RestMetricsHttpServer, persistence_runtime: PersistenceRuntime) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            await persistence_runtime.readiness.ensure_ready()
            try:
                await metrics_server.start()
            except BaseException:
                await metrics_server.stop()
                raise
            try:
                yield
            finally:
                await metrics_server.stop()
                flush_logging()
        finally:
            await persistence_runtime.shutdown()
    return lifespan

def create_app(*args: Any, **kwargs: Any) -> FastAPI:
    create_app_arguments = _resolve_create_app_arguments(*args, **kwargs)
    app_settings = create_app_arguments.settings or load_app_config('.env')
    persistence_runtime = ConfiguredPersistenceRuntimeProvider(app_settings.connector_store).create()
    dependency_factories = ConnectorApiDependencyFactories.from_settings(app_settings, persistence_runtime, create_app_arguments.connector_registrations)
    dependency_factories.validate_startup()
    metrics_recorder = PrometheusRestMetricsRecorder()
    metrics_server = RestMetricsHttpServer(metrics_recorder, app_settings.rest.metrics_port)
    app = LifespanRootApiAppFactory(app_settings, lifespan=_create_lifespan(metrics_server, persistence_runtime)).create()
    _mount_admin_app(app, app_settings, dependency_factories, metrics_recorder, app_settings)
    _mount_system_app(app, dependency_factories)
    return app
