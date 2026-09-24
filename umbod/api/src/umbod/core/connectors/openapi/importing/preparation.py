import re
from typing import Protocol
from urllib.parse import urlsplit

from pydantic import ConfigDict

from umbod.core.connectors.openapi.management.models import ImportOpenApiCatalog
from umbod.core.connectors.openapi.models import ImportedOpenApiCandidate
from umbod.proxies import Model


class PreparedOpenApiImport(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    connector_id: str
    source_document: dict[str, object]
    candidate: ImportedOpenApiCandidate
    approved_hosts: tuple[str, ...]
    selected_server_url: str
    operation_ids: tuple[str, ...]


class OpenApiImportPreparer(Protocol):
    def prepare(self, request: ImportOpenApiCatalog) -> PreparedOpenApiImport: ...


class OpenApiServerSelectionRequired(ValueError):
    code = "openapi_server_selection_required"


class DefaultOpenApiImportPreparer:
    def prepare(self, request: ImportOpenApiCatalog) -> PreparedOpenApiImport:
        approved_hosts = self._normalize_hosts(request.approved_hosts)
        eligible_servers = self._eligible_servers(request.candidate, approved_hosts)
        return PreparedOpenApiImport(
            connector_id=request.connector_id,
            source_document=request.source_document,
            candidate=request.candidate,
            approved_hosts=approved_hosts,
            selected_server_url=self._select_server_url(
                request.selected_server_url, eligible_servers
            ),
            operation_ids=self._validated_operation_ids(request.candidate),
        )

    def _eligible_servers(
        self,
        candidate: ImportedOpenApiCandidate,
        approved_hosts: tuple[str, ...],
    ) -> tuple[str, ...]:
        eligible_servers = tuple(
            server_url
            for server_url in candidate.server_candidates
            if self._server_has_approved_host(server_url, approved_hosts)
        )
        if not candidate.server_candidates and len(approved_hosts) == 1:
            return (f"https://{approved_hosts[0]}",)
        return eligible_servers

    def _select_server_url(
        self,
        selected_server_url: str | None,
        eligible_servers: tuple[str, ...],
    ) -> str:
        if selected_server_url is None:
            if len(eligible_servers) != 1:
                raise OpenApiServerSelectionRequired(
                    "OpenAPI import requires one selected eligible server"
                )
            return eligible_servers[0]
        if selected_server_url not in eligible_servers:
            raise ValueError("Selected server must use an approved exact host")
        return selected_server_url

    def _validated_operation_ids(
        self, candidate: ImportedOpenApiCandidate
    ) -> tuple[str, ...]:
        operation_ids = tuple(
            endpoint.operation_id.strip() for endpoint in candidate.endpoints
        )
        if any(not operation_id for operation_id in operation_ids):
            raise ValueError("Operation IDs must not be empty")
        if len(set(operation_ids)) != len(operation_ids):
            raise ValueError("Operation IDs must be unique")
        if operation_ids != tuple(
            endpoint.operation_id for endpoint in candidate.endpoints
        ):
            raise ValueError("Operation IDs must be stable normalized identifiers")
        return tuple(sorted(operation_ids))

    def _server_has_approved_host(
        self, server_url: str, approved_hosts: tuple[str, ...]
    ) -> bool:
        hostname = urlsplit(server_url).hostname
        return hostname is not None and hostname.lower().rstrip(".") in approved_hosts

    def _normalize_hosts(self, hosts: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(
            sorted(
                {
                    normalized_host
                    for host in hosts
                    if (normalized_host := host.strip().lower())
                }
            )
        )
        hostname_pattern = re.compile(
            r"^(?=.{1,253}$)(?!-)(?:[a-z0-9-]{1,63}\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
        )
        if not normalized or any(
            hostname_pattern.fullmatch(host) is None for host in normalized
        ):
            raise ValueError("Approved hosts must contain exact hostnames")
        return normalized
