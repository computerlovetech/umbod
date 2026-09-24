from umbod.mcp.connectors.tools.deployment_modes.codemode.deployment import (
    CodeModeConnectorToolDeploymentFactory,
)
from umbod.mcp.connectors.tools.deployment_modes.contract import (
    ConnectorToolDeploymentFactory,
    ConnectorToolExposureMode,
)
from umbod.mcp.connectors.tools.deployment_modes.flat.deployment import (
    FlatConnectorToolDeploymentFactory,
)
from umbod.mcp.connectors.tools.deployment_modes.gateway.deployment import (
    GatewayConnectorToolDeploymentFactory,
)


def connector_tool_deployment_factory(
    exposure_mode: ConnectorToolExposureMode,
    code_execution_timeout_seconds: float,
    maximum_uploaded_file_bytes: int,
) -> ConnectorToolDeploymentFactory:
    factories: dict[ConnectorToolExposureMode, ConnectorToolDeploymentFactory] = {
        "flat": FlatConnectorToolDeploymentFactory(maximum_uploaded_file_bytes),
        "gateway": GatewayConnectorToolDeploymentFactory(),
        "codemode": CodeModeConnectorToolDeploymentFactory(code_execution_timeout_seconds),
    }
    return factories[exposure_mode]
