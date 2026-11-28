from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, Request

from umbod.config import AppConfig
from umbod.config.system_settings import (
    ConfiguredSystemSettingsDefaults,
    configured_provider_membership_claim,
)
from umbod.core.persistence import PersistenceReadiness
from umbod.core.system_settings import (
    SettingsStorageUnavailable,
    SystemSettingsService,
    create_system_settings_service_with_defaults,
)
from umbod.core.system_settings.provider_group_mappings import (
    ProviderGroupMappingsService,
    create_provider_group_mappings_service,
)
from umbod.rest.authentication.authorization import JwtClaims
from umbod.rest.authentication.deps import (
    ADMIN_AUTHORIZED_STATE_KEY,
    get_verified_access_claims,
)
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.instance_configuration.dependencies import get_app_config

type AdministratorRole = Literal["administrator"]


def require_settings_administrator(
    request: Request,
    config: Annotated[AppConfig, Depends(get_app_config)],
    _claims: Annotated[JwtClaims, Depends(get_verified_access_claims)],
) -> AdministratorRole:
    if (
        config.admin_authentication.mode == "disabled"
        or getattr(request.state, ADMIN_AUTHORIZED_STATE_KEY, False) is not True
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return "administrator"


@dataclass(frozen=True)
class AuthorizedSettings[Service]:
    actor: AdministratorRole
    service: Service
    readiness: PersistenceReadiness

    async def ensure_ready(self) -> None:
        try:
            await self.readiness.ensure_ready()
        except Exception:
            raise SettingsStorageUnavailable() from None


def get_authorized_system_settings(
    actor: Annotated[AdministratorRole, Depends(require_settings_administrator)],
    config: Annotated[AppConfig, Depends(get_app_config)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> AuthorizedSettings[SystemSettingsService]:
    runtime = factories.persistence_runtime
    return AuthorizedSettings(
        actor=actor,
        service=create_system_settings_service_with_defaults(
            runtime.database, defaults=ConfiguredSystemSettingsDefaults(config)
        ),
        readiness=runtime.readiness,
    )


def get_authorized_provider_group_mappings(
    actor: Annotated[AdministratorRole, Depends(require_settings_administrator)],
    config: Annotated[AppConfig, Depends(get_app_config)],
    factories: Annotated[
        ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)
    ],
) -> AuthorizedSettings[ProviderGroupMappingsService]:
    runtime = factories.persistence_runtime
    return AuthorizedSettings(
        actor=actor,
        service=create_provider_group_mappings_service(
            runtime.database,
            provider_claim=configured_provider_membership_claim(config),
        ),
        readiness=runtime.readiness,
    )
