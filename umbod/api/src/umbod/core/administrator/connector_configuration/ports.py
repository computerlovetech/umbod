from typing import Protocol

from .requests import ReadConnectorConfiguration, UpsertConnectorConfiguration
from .results import ConfigurationResult


class ConnectorConfigurationReader(Protocol):
    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        ...


class ConnectorConfigurationMutationWriter(Protocol):
    async def upsert(self, request: UpsertConnectorConfiguration) -> ConfigurationResult:
        ...


class AdministratorConnectorConfiguration(Protocol):
    async def read(self, request: ReadConnectorConfiguration) -> ConfigurationResult:
        ...

    async def upsert(self, request: UpsertConnectorConfiguration) -> ConfigurationResult:
        ...
