from typing import Annotated

from fastapi import Depends, HTTPException

from umbod.core.harness_plugins.installers import HarnessInstallerService, InstallerConfiguration
from umbod.core.harness_plugins.ports import InstallerSourceReader, PackageResourceReader
from umbod.core.harness_plugins.service import HarnessPackageService
from umbod.rest.dependencies import get_connector_api_dependency_factories
from umbod.rest.factories import ConnectorApiDependencyFactories
from umbod.rest.install.resources import BundledInstallerSourceReader, BundledPackageResourceReader


def installer_unavailable() -> HTTPException:
    return HTTPException(
        status_code=503, detail="Installation script is unavailable",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


def get_installer_sources() -> InstallerSourceReader:
    return BundledInstallerSourceReader()


def get_installer_service(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    sources: Annotated[InstallerSourceReader, Depends(get_installer_sources)],
) -> HarnessInstallerService:
    try:
        endpoints = factories.settings.endpoints
        configuration = InstallerConfiguration(api_origin=endpoints.api_base_url, endpoint=endpoints.mcp_base_url)
        return HarnessInstallerService(configuration, sources)
    except ValueError:
        raise installer_unavailable() from None


def get_package_resources() -> PackageResourceReader:
    return BundledPackageResourceReader()


def get_package_service(
    factories: Annotated[ConnectorApiDependencyFactories, Depends(get_connector_api_dependency_factories)],
    resources: Annotated[PackageResourceReader, Depends(get_package_resources)],
) -> HarnessPackageService:
    try:
        return HarnessPackageService(factories.settings.endpoints.mcp_base_url, resources)
    except ValueError:
        raise HTTPException(
            status_code=503, detail="Installation endpoint is not configured",
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        ) from None
