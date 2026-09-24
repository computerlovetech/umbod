class DownstreamConnectorNotFoundError(KeyError):
    pass


class DownstreamConnectorConflictError(ValueError):
    pass


class DownstreamPublicPathConflictError(DownstreamConnectorConflictError):
    pass


class DownstreamConnectorUnavailableError(DownstreamConnectorConflictError):
    pass


class DownstreamCredentialMissingError(ValueError):
    pass


class DownstreamPermissionGrantConflict(ValueError):
    def __init__(self, connector_id: str, affected_group_ids: tuple[str, ...]) -> None:
        self.connector_id = connector_id
        self.affected_group_ids = affected_group_ids
        super().__init__("Active permission grants prevent deleting the downstream connector")
