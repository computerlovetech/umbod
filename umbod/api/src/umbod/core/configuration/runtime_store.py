from umbod.proxies import Model


class InMemoryConnectorCurrentConfigurationStore:
    def __init__(self) -> None:
        self._configurations: dict[str, Model] = {}

    async def get_current_configuration(self, connector_id: str) -> Model | None:
        return self._configurations.get(connector_id)

    async def save_current_configuration(self, connector_id: str, configuration: Model) -> None:
        self._configurations[connector_id] = configuration

    async def delete_current_configuration(self, connector_id: str) -> None:
        self._configurations.pop(connector_id, None)
