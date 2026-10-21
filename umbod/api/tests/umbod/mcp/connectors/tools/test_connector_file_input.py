import base64
from collections.abc import Callable
from hashlib import sha256
from inspect import signature
from typing import Annotated, Optional

import pytest
from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from pydantic import ValidationError

from umbod.core.configuration import InMemoryConnectorCurrentConfigurationStore
from umbod.core.connectors.native.runtime.tools import ConcreteConnectorToolMapping
from umbod.core.invocation import ConnectorInvocation, ConnectorInvocationPolicy, DirectInvocationDecision
from umbod.mcp.connectors.native.tools import register_connector_tools
from umbod.mcp.logging import create_default_mcp_tool_invocation_log_sink
from umbod.mcp.connectors.native.tools.deployment_modes.flat.exposure import FastMcpConnectorToolExposureLifecycle
from umbod.mcp.connectors.native.tools.file_app import ConnectorFileAppRegistration, FastMcpConnectorFileToolRegistrar
from umbod.mcp.connectors.native.tools.file_input import DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES, StrictUploadedFilePayloadAdapter, UploadedFilePayloadConverter, UploadedFileWirePayload
from umbod_sdk.connectors.plugin_api import Connector, UploadedFile
from umbod_sdk.connectors.proxies import Model
from tests.umbod.mcp.connectors.tools.test_connector_tool_exposure_mode_acceptance import InMemoryConnectorPublishingStore


def _file_connector(operation: Callable[..., object]) -> Connector:
    connector = Connector(
        id="files",
        name="Files",
        description="Process uploaded files.",
        capability_description="Process uploaded files.",
        configuration=Model,
    )

    @connector.configuration_check
    def check_configuration(configuration: Model) -> bool:
        return True

    connector.tool(
        description="Process an uploaded file.",
        parameters={
            name: "Uploaded file input."
            for name in signature(operation).parameters
            if name != "configuration"
        },
    )(operation)
    return connector


class RecordingInvocationPolicy:
    def __init__(self) -> None:
        self.invocations: list[ConnectorInvocation] = []

    async def evaluate(self, invocation: ConnectorInvocation) -> DirectInvocationDecision:
        self.invocations.append(invocation)
        return DirectInvocationDecision()


@pytest.mark.parametrize(
    ("media_type", "data"),
    [
        ("application/pdf", b"%PDF-1.7\n"),
        ("image/jpeg", b"\xff\xd8\xff\xe0"),
        ("image/png", b"\x89PNG\r\n\x1a\n"),
        ("image/gif", b"GIF89a"),
        ("image/webp", b"RIFF\x04\x00\x00\x00WEBP"),
    ],
)
def test_converter_creates_immutable_uploaded_file(media_type: str, data: bytes) -> None:
    converter: UploadedFilePayloadConverter = StrictUploadedFilePayloadAdapter(
        DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES
    )
    payload = UploadedFileWirePayload(name="document.bin", type=media_type, size=len(data), data=base64.b64encode(data).decode("ascii"))

    uploaded = converter.convert(payload)

    assert isinstance(uploaded, UploadedFile)
    assert uploaded.read() == data
    assert uploaded.size == len(data)


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "../secret.pdf", "type": "application/pdf", "size": 8, "data": "JVBERi0x"},
        {"name": "secret.pdf", "type": "text/plain", "size": 8, "data": "JVBERi0x"},
        {"name": "secret.pdf", "type": "application/pdf", "size": 9, "data": "JVBERi0x"},
        {"name": "secret.pdf", "type": "application/pdf", "size": 6, "data": "bm90cGRm"},
        {"name": "secret.pdf", "type": "application/pdf", "size": 1, "data": "!!!!"},
    ],
)
def test_converter_rejects_unsafe_or_deceptive_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        StrictUploadedFilePayloadAdapter(DEFAULT_MAXIMUM_UPLOADED_FILE_BYTES).convert(
            UploadedFileWirePayload.model_validate(payload)
        )


def test_converter_rejects_encoded_payload_before_decoding_when_oversized() -> None:
    payload = UploadedFileWirePayload(name="large.pdf", type="application/pdf", size=9, data=base64.b64encode(b"%PDF-1234").decode("ascii"))

    with pytest.raises(ValueError, match="maximum"):
        StrictUploadedFilePayloadAdapter(maximum_bytes=8).convert(payload)


def test_wire_payload_rejects_empty_file() -> None:
    with pytest.raises(ValidationError):
        UploadedFileWirePayload(name="empty.pdf", type="application/pdf", size=0, data="")


@pytest.mark.asyncio
async def test_safe_arguments_distinguish_files_with_identical_metadata() -> None:
    received_files: list[UploadedFile] = []

    def upload(file: UploadedFile) -> dict[str, object]:
        received_files.append(file)
        return {"filename": file.filename}

    connector = _file_connector(upload)
    configuration_store = InMemoryConnectorCurrentConfigurationStore()
    await configuration_store.save_current_configuration("files", Model())
    publishing_store = InMemoryConnectorPublishingStore()
    await publishing_store.publish_connector("files")
    recording_policy = RecordingInvocationPolicy()
    policy: ConnectorInvocationPolicy = recording_policy
    mcp = FastMCP("file-policy-test")
    await register_connector_tools(
        mcp,
        invocation_policy=policy,
        connector_registrations=[connector.registration()],
        connector_configuration_store=configuration_store,
        connector_publishing_store=publishing_store,
        connector_tool_mappings=[ConcreteConnectorToolMapping(
            connector_id="files",
            operation_name="upload",
            description="Process an uploaded file.",
            operation=upload,
            parameters={},
        )],
        tool_invocation_log_sink=create_default_mcp_tool_invocation_log_sink(),
    )
    backend_name = next(
        tool.name for tool in await mcp.list_tools() if tool.name.startswith("submit_")
    )
    contents = (b"%PDF-first", b"%PDF-other")
    for data in contents:
        await mcp.call_tool(backend_name, {"file": {
            "name": "same.pdf",
            "type": "application/pdf",
            "size": len(data),
            "data": base64.b64encode(data).decode("ascii"),
        }})

    assert [invocation.arguments for invocation in recording_policy.invocations] == [
        {"file": {
            "filename": "same.pdf",
            "media_type": "application/pdf",
            "size": len(data),
            "sha256": sha256(data).hexdigest(),
        }}
        for data in contents
    ]
    first, second = recording_policy.invocations
    assert first.arguments["file"]["sha256"] != second.arguments["file"]["sha256"]
    assert len(received_files) == 2
    assert all(isinstance(file, UploadedFile) for file in received_files)
    assert [file.read() for file in received_files] == list(contents)
    assert all(file.filename == "same.pdf" for file in received_files)
    assert all(file.media_type == "application/pdf" for file in received_files)


def test_annotated_uploaded_file_is_allowed() -> None:
    def operation(file: Annotated[UploadedFile, "input"]) -> None:
        return None

    _file_connector(operation).registration()


@pytest.mark.parametrize(
    "annotation",
    [Optional[UploadedFile], list[UploadedFile]],
)
def test_wrapped_uploaded_file_is_rejected(annotation: object) -> None:
    def operation(file: object) -> None:
        return None

    parameter = signature(operation).parameters["file"].replace(annotation=annotation)
    operation.__signature__ = signature(operation).replace(parameters=[parameter])

    with pytest.raises(ValueError, match="directly"):
        _file_connector(operation).registration()


def test_file_tool_with_another_public_parameter_is_rejected() -> None:
    def operation(file: UploadedFile, title: str) -> None:
        return None

    with pytest.raises(ValueError, match="no other public parameters|only one required"):
        _file_connector(operation).registration()


def test_file_tool_allows_hidden_configuration_parameter() -> None:
    def operation(file: UploadedFile, configuration: object) -> None:
        return None

    _file_connector(operation).registration()


def test_multiple_and_default_uploaded_files_are_rejected() -> None:
    def multiple(first: UploadedFile, second: UploadedFile) -> None:
        return None

    def default(file: UploadedFile) -> None:
        return None

    default_parameter = signature(default).parameters["file"].replace(default=None)
    default.__signature__ = signature(default).replace(parameters=[default_parameter])

    with pytest.raises(ValueError, match="exactly one"):
        _file_connector(multiple).registration()
    with pytest.raises(ValueError, match="required"):
        _file_connector(default).registration()


class RecordingInvoker:
    def __init__(self) -> None:
        self.arguments: dict[str, object] = {}

    async def invoke(self, arguments: dict[str, object]) -> ToolResult:
        self.arguments = arguments
        return ToolResult(structured_content={"ok": True})


@pytest.mark.asyncio
async def test_two_file_apps_have_unique_app_only_backends_and_removal() -> None:
    def upload(file: UploadedFile) -> dict[str, object]:
        return {"filename": file.filename}

    mcp = FastMCP("file-tools")
    registrations: dict[str, ConnectorFileAppRegistration] = {}
    registrar = FastMcpConnectorFileToolRegistrar(12, registrations)
    for connector_id, operation_name in (("alpha", "upload"), ("beta", "upload")):
        mapping = ConcreteConnectorToolMapping(
            connector_id=connector_id,
            operation_name=operation_name,
            description="Upload a file.",
            operation=upload,
            parameters={},
        )
        registrar.register(mcp, mapping, RecordingInvoker())

    tools = await mcp.list_tools()
    public_tools = [tool for tool in tools if tool.name in {"alpha_upload", "beta_upload"}]
    backend_tools = [tool for tool in tools if tool.name.startswith("submit_")]

    assert len(public_tools) == 2
    assert len(backend_tools) == 2
    assert len({tool.name for tool in backend_tools}) == 2
    assert all(tool.meta["ui"]["visibility"] == ["app"] for tool in backend_tools)
    assert all(tool.parameters["properties"] == {} for tool in public_tools)

    lifecycle = FastMcpConnectorToolExposureLifecycle(mcp, registrations)
    removed_registration = registrations["alpha_upload"]
    lifecycle.remove_tool("alpha_upload")
    remaining_names = {tool.name for tool in await mcp.list_tools()}

    assert "alpha_upload" not in remaining_names
    assert not any(
        tool.meta.get("fastmcp", {}).get("app") == "connector-file-alpha-upload"
        for tool in await mcp.list_tools()
    )
    assert removed_registration.eligible is False

    alpha_mapping = ConcreteConnectorToolMapping(
        connector_id="alpha",
        operation_name="upload",
        description="Upload a file.",
        operation=upload,
        parameters={},
    )
    alpha_invoker = RecordingInvoker()
    registrar.register(mcp, alpha_mapping, alpha_invoker)
    reenabled_tools = await mcp.list_tools()

    assert registrations["alpha_upload"] is removed_registration
    assert len([tool for tool in reenabled_tools if tool.name == "alpha_upload"]) == 1
    assert len([tool for tool in reenabled_tools if tool.name.startswith("submit_")]) == 2
    assert removed_registration.eligible is True


@pytest.mark.asyncio
async def test_backend_invocation_validates_file_and_denies_while_disabled() -> None:
    def upload(file: UploadedFile) -> dict[str, object]:
        return {"filename": file.filename}

    mapping = ConcreteConnectorToolMapping(
        connector_id="images",
        operation_name="inspect",
        description="Inspect an image.",
        operation=upload,
        parameters={},
    )
    mcp = FastMCP("file-tools")
    registrations: dict[str, ConnectorFileAppRegistration] = {}
    invoker = RecordingInvoker()
    registrar = FastMcpConnectorFileToolRegistrar(12, registrations)
    registrar.register(mcp, mapping, invoker)
    backend_name = next(
        tool.name for tool in await mcp.list_tools() if tool.name.startswith("submit_")
    )
    image = b"\x89PNG\r\n\x1a\n\xff\x00"
    payload = {
        "file": {
            "name": "image.png",
            "type": "image/png",
            "size": len(image),
            "data": base64.b64encode(image).decode("ascii"),
        }
    }

    await mcp.call_tool(backend_name, payload)

    uploaded = invoker.arguments["file"]
    assert isinstance(uploaded, UploadedFile)
    assert uploaded.read() == image

    registrations["images_inspect"].disable()
    with pytest.raises(Exception, match="no longer eligible|not found|Unknown"):
        await mcp.call_tool(backend_name, payload)

    registrar.register(mcp, mapping, invoker)
    await mcp.call_tool(backend_name, payload)
    assert isinstance(invoker.arguments["file"], UploadedFile)
