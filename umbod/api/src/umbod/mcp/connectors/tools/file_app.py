from hashlib import sha256
from inspect import Parameter, Signature, signature
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import FastMCPApp
from fastmcp.tools import ToolResult
from prefab_ui.actions import ShowToast
from prefab_ui.actions.mcp import CallTool
from prefab_ui.app import PrefabApp
from prefab_ui.components import Button, Card, CardContent, CardHeader, Column, DropZone, H3, Muted
from prefab_ui.components.control_flow import If
from prefab_ui.rx import ERROR, RESULT, STATE, Rx

from umbod.core.connectors.native.runtime.tools import ConnectorToolMapping
from umbod.mcp.connectors.tools.definition.naming import _tool_name
from umbod.mcp.connectors.tools.file_input import StrictUploadedFilePayloadAdapter, UploadedFilePayloadConverter, UploadedFileWirePayload, uploaded_file_parameter_name
from umbod.mcp.connectors.tools.invocation.ports import ConnectorToolInvoker

FILE_APP_DESCRIPTION_SUFFIX = " Select one file in the app, submit it, and wait for the result."


class ConnectorFileAppRegistration:
    def __init__(
        self,
        provider: FastMCPApp,
        component_names: frozenset[str],
        eligible: bool,
    ) -> None:
        self.provider = provider
        self.component_names = component_names
        self.eligible = eligible

    def disable(self) -> None:
        self.eligible = False
        self.provider.disable(names=set(self.component_names))

    def enable(self) -> None:
        self.provider.enable(names=set(self.component_names))
        self.eligible = True


class ConnectorFileInputApp:
    def __init__(
        self,
        mapping: ConnectorToolMapping,
        invoker: ConnectorToolInvoker,
        converter: UploadedFilePayloadConverter,
        maximum_bytes: int,
    ) -> None:
        self._mapping = mapping
        self._invoker = invoker
        self._converter = converter
        self._maximum_bytes = maximum_bytes

    def register(self, mcp: FastMCP) -> ConnectorFileAppRegistration:
        mapping = self._mapping
        file_parameter = uploaded_file_parameter_name(mapping.operation)
        if file_parameter is None:
            raise ValueError("connector file app requires an UploadedFile parameter")
        app_name = f"connector-file-{mapping.connector_id}-{mapping.operation_name}"
        app = FastMCPApp(app_name)
        backend_name = f"submit_{sha256(app_name.encode('utf-8')).hexdigest()[:16]}"
        registration = ConnectorFileAppRegistration(
            app,
            frozenset({_tool_name(mapping), backend_name}),
            True,
        )

        async def submit_file(**arguments: Any) -> ToolResult:
            if not registration.eligible:
                raise PermissionError("Connector file tool is no longer eligible")
            payload = UploadedFileWirePayload.model_validate(arguments.pop(file_parameter))
            arguments[file_parameter] = self._converter.convert(payload)
            return await self._invoker.invoke(arguments)

        submit_file.__signature__ = _backend_signature(mapping.operation, file_parameter)
        submit_file.__annotations__ = _backend_annotations(mapping.operation, file_parameter)
        app.tool(name=backend_name, description="Validate the selected file and invoke the connector tool.")(submit_file)

        @app.ui(
            name=_tool_name(mapping),
            description=mapping.description + FILE_APP_DESCRIPTION_SUFFIX,
            tags={"connector", mapping.connector_id},
        )
        def open_file_input() -> PrefabApp:
            with Card(css_class="max-w-lg mx-auto") as view:
                with CardHeader():
                    H3(mapping.description)
                with CardContent(), Column(gap=4):
                    Muted("The selected file is sent directly for this invocation and is not stored.")
                    DropZone(
                        name="pending",
                        label="Select one file",
                        description=f"PDF, JPEG, PNG, GIF, or WebP; maximum {_file_size_label(self._maximum_bytes)}",
                        multiple=False,
                        max_size=self._maximum_bytes,
                    )
                    with If(STATE.pending.length()):
                        submit_action = CallTool(
                            backend_name,
                            arguments={file_parameter: Rx("pending[0]")},
                            on_success=ShowToast("File processed", variant="success"),
                            on_error=ShowToast(ERROR, variant="error"),
                        )
                        Button("Submit", on_click=submit_action)
            return PrefabApp(view=view, state={"pending": [], "result": RESULT})

        mcp.add_provider(app)
        return registration


def _file_size_label(maximum_bytes: int) -> str:
    if maximum_bytes % (1024 * 1024) == 0:
        return f"{maximum_bytes // (1024 * 1024)} MiB"
    return f"{maximum_bytes} bytes"


def _backend_signature(operation: object, file_parameter: str) -> Signature:
    parameters: list[Parameter] = []
    for parameter in signature(operation).parameters.values():
        if parameter.name == "configuration":
            continue
        if parameter.name == file_parameter:
            parameters.append(parameter.replace(annotation=UploadedFileWirePayload))
        else:
            parameters.append(parameter)
    return Signature(parameters=parameters, return_annotation=ToolResult)


def _backend_annotations(operation: object, file_parameter: str) -> dict[str, object]:
    annotations: dict[str, object] = {}
    for parameter in signature(operation).parameters.values():
        if parameter.name == "configuration":
            continue
        annotations[parameter.name] = UploadedFileWirePayload if parameter.name == file_parameter else parameter.annotation
    annotations["return"] = ToolResult
    return annotations


class FastMcpConnectorFileToolRegistrar:
    def __init__(
        self,
        maximum_bytes: int,
        registrations: dict[str, ConnectorFileAppRegistration],
    ) -> None:
        self._maximum_bytes = maximum_bytes
        self._converter = StrictUploadedFilePayloadAdapter(maximum_bytes)
        self._registrations = registrations

    def register(
        self,
        mcp: FastMCP,
        mapping: ConnectorToolMapping,
        invoker: ConnectorToolInvoker,
    ) -> None:
        tool_name = _tool_name(mapping)
        existing_registration = self._registrations.get(tool_name)
        if existing_registration is not None:
            existing_registration.enable()
            return
        self._registrations[tool_name] = ConnectorFileInputApp(
            mapping,
            invoker,
            self._converter,
            self._maximum_bytes,
        ).register(mcp)
