from umbod.core.connectors.openapi.importing import OpenApiCandidateImporter, OpenApiImportPreparer
from umbod.core.connectors.openapi.management.configuration import OpenApiBearerConfiguration, OpenApiConfigurationPort
from umbod.core.connectors.openapi.management.models import CreateOpenApiConnector, ImportOpenApiCatalog, OpenApiConnector
from umbod.core.connectors.openapi.management.setup_ports import (
    OpenApiSetupCleanupFailed,
    OpenApiSetupFailed,
    OpenApiSetupInvalidRequest,
    OpenApiSetupManagementPort,
    SetupOpenApiConnector,
)
from umbod.core.connectors.openapi.errors import OpenApiCandidateValidationError


class OpenApiConnectorSetupService:
    def __init__(
        self, management: OpenApiSetupManagementPort, importer: OpenApiCandidateImporter,
        preparer: OpenApiImportPreparer, configuration: OpenApiConfigurationPort,
    ) -> None:
        self._management = management
        self._importer = importer
        self._preparer = preparer
        self._configuration = configuration

    async def setup(self, request: SetupOpenApiConnector) -> OpenApiConnector:
        try:
            if not request.display_name.strip():
                raise ValueError("Display name must not be blank")
            if request.authentication_type == "bearer":
                OpenApiBearerConfiguration(bearer_token=request.bearer_token)
            candidate = self._importer.import_candidate(request.document)
            import_request = ImportOpenApiCatalog(
                connector_id="pending-setup", source_document=request.document,
                candidate=candidate, approved_hosts=request.approved_hosts,
            )
            self._preparer.prepare(import_request)
            connector = await self._management.create_connector(CreateOpenApiConnector(
                display_name=request.display_name, tool_name_prefix=request.tool_name_prefix,
                capability_description=request.capability_description,
            ))
        except (ValueError, OpenApiCandidateValidationError) as error:
            raise OpenApiSetupInvalidRequest("Invalid OpenAPI setup request") from error
        except Exception as error:
            raise OpenApiSetupFailed("OpenAPI setup failed") from error
        try:
            await self._management.import_catalog(import_request.model_copy(update={"connector_id": connector.connector_id}))
            if request.authentication_type == "none":
                await self._configuration.clear(connector.connector_id)
            else:
                await self._configuration.configure(connector.connector_id, request.bearer_token)
            return await self._management.get_connector(connector.connector_id)
        except Exception as error:
            await self._compensate(connector.connector_id)
            raise OpenApiSetupFailed("OpenAPI setup failed") from error

    async def _compensate(self, connector_id: str) -> None:
        cleanup_failed = False
        try:
            await self._configuration.clear(connector_id)
        except Exception:
            cleanup_failed = True
        try:
            await self._management.delete_connector(connector_id)
        except Exception:
            cleanup_failed = True
        if cleanup_failed:
            raise OpenApiSetupCleanupFailed(connector_id)
