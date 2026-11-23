from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from umbod.core.harness_plugins import Harness
from umbod.core.harness_plugins.installers import HarnessInstallerService
from umbod.core.harness_plugins.ports import ScriptKind
from umbod.core.harness_plugins.service import HarnessPackageService
from umbod.rest.install.deps import get_installer_service, get_package_service, installer_unavailable
from umbod.rest.telemetry_setup.deps import get_telemetry_setup_configuration
from umbod.rest.telemetry_setup.models import TelemetrySetup

router = APIRouter(prefix="/v1", tags=["install"])
PackageService = Annotated[HarnessPackageService, Depends(get_package_service)]
InstallerService = Annotated[HarnessInstallerService, Depends(get_installer_service)]
InstallerTelemetry = Annotated[TelemetrySetup, Depends(get_telemetry_setup_configuration)]


def installer_download(
    request: Request, harness: Harness, service: HarnessInstallerService, kind: ScriptKind, telemetry: TelemetrySetup,
) -> Response:
    try:
        content = service.render(harness, kind, telemetry.logs_endpoint if telemetry.status == "available" else "")
    except (OSError, ValueError, LookupError):
        raise installer_unavailable() from None
    response = download(request, content, harness, "install." + kind, "text/plain")
    response.headers["Content-Disposition"] = f'inline; filename="umbod-{harness}-install.{kind}"'
    return response


@router.api_route("/{harness}/install.sh", methods=["GET", "HEAD"])
def bash_installer(request: Request, harness: Harness, service: InstallerService, telemetry: InstallerTelemetry) -> Response:
    return installer_download(request, harness, service, "sh", telemetry)


@router.api_route("/{harness}/install.ps1", methods=["GET", "HEAD"])
def powershell_installer(request: Request, harness: Harness, service: InstallerService, telemetry: InstallerTelemetry) -> Response:
    return installer_download(request, harness, service, "ps1", telemetry)


def download(
    request: Request, content: str | bytes, harness: Harness, filename: str, media_type: str,
) -> Response:
    response = Response(content=content, media_type=media_type, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="umbod-{harness}-{filename}"',
    })
    if request.method == "HEAD":
        response.body = b""
    return response


@router.api_route("/{harness}/package.zip", methods=["GET", "HEAD"])
def package_zip(request: Request, harness: Harness, service: PackageService) -> Response:
    return download(request, service.package(harness), harness, "package.zip", "application/zip")


@router.api_route("/{harness}/package.sha256", methods=["GET", "HEAD"])
def package_checksum(request: Request, harness: Harness, service: PackageService) -> Response:
    return download(request, service.checksum(harness) + "\n", harness, "package.sha256", "text/plain")


@router.api_route("/{harness}/marketplace.txt", methods=["GET", "HEAD"])
def package_marketplace(request: Request, harness: Harness, service: PackageService) -> Response:
    return download(request, service.marketplace + "\n", harness, "marketplace.txt", "text/plain")


@router.api_route("/{harness}/endpoint.txt", methods=["GET", "HEAD"])
def package_endpoint(request: Request, harness: Harness, service: PackageService) -> Response:
    return download(request, service.endpoint + "\n", harness, "endpoint.txt", "text/plain")
