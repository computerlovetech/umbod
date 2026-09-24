from fastapi import Request

from umbod.rest.factories import ConnectorApiDependencyFactories


DEPENDENCY_FACTORIES_STATE_KEY = "connector_api_dependency_factories"


def get_connector_api_dependency_factories(request: Request) -> ConnectorApiDependencyFactories:
    factories = getattr(request.state, DEPENDENCY_FACTORIES_STATE_KEY, None)
    if not isinstance(factories, ConnectorApiDependencyFactories):
        raise RuntimeError("Connector API dependency factories are not wired")
    return factories
