from .models import AdministratorPrincipal, ConnectorDesiredState, ConnectorReference, _StrictModel


class ReadConnectorConfiguration(_StrictModel):
    principal: AdministratorPrincipal
    connector: ConnectorReference


class UpsertConnectorConfiguration(_StrictModel):
    principal: AdministratorPrincipal
    connector: ConnectorReference
    desired_state: ConnectorDesiredState
