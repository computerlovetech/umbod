from .ports import ConnectorConfigurationMutationWriter, ConnectorConfigurationReader
from .requests import ReadConnectorConfiguration, UpsertConnectorConfiguration
from .results import ConfigurationResult


class AdministratorConnectorConfigurationService:
    def __init__(
        self,
        reader: ConnectorConfigurationReader,
        mutation_writer: ConnectorConfigurationMutationWriter,
    ) -> None:
        self._reader = reader
        self._mutation_writer = mutation_writer

    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        return await self._reader.read(request)

    async def upsert(self, request: UpsertConnectorConfiguration) -> ConfigurationResult:
        if request.desired_state.is_empty():
            return await self._reader.read(
                ReadConnectorConfiguration(
                    principal=request.principal,
                    connector=request.connector,
                )
            )
        return await self._mutation_writer.upsert(request)
