import base64
import ipaddress
import re
import shlex
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, field_validator

from umbod.core.harness_plugins.ports import InstallerSourceReader, ScriptKind
from umbod.core.harness_plugins.rendering import Harness, normalize_endpoint


def normalize_public_origin(value: str) -> str:
    normalize_endpoint(value)
    parsed = urlsplit(value)
    if parsed.path not in {"", "/"}:
        raise ValueError("The public API URL must be an origin")
    host = parsed.hostname
    if not host:
        raise ValueError("The public API origin must have a host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        labels = host.encode("idna").decode("ascii").rstrip(".").split(".")
        if any(not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label) for label in labels):
            raise ValueError("The public API origin has an invalid host") from None
    if any(ord(character) == 127 for character in value):
        raise ValueError("The public API origin contains control characters")
    return value.rstrip("/")


class InstallerConfiguration(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_origin: str
    endpoint: str

    @field_validator("api_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        return normalize_public_origin(value)

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        endpoint = normalize_endpoint(value)
        parsed = urlsplit(endpoint)
        normalize_public_origin(f"{parsed.scheme}://{parsed.netloc}")
        if any(ord(character) == 127 for character in endpoint) or re.search(r"%0[0-9a-f]|%1[0-9a-f]|%7f", endpoint, re.IGNORECASE):
            raise ValueError("The MCP endpoint contains control characters")
        return endpoint

    @property
    def package_base_url(self) -> str:
        return self.api_origin + "/api/install/v1"


def powershell_literal(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return "([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded + "')))"


class HarnessInstallerService:
    def __init__(self, configuration: InstallerConfiguration, sources: InstallerSourceReader) -> None:
        self._configuration = configuration
        self._sources = sources

    def render(self, harness: Harness, kind: ScriptKind, logs_endpoint: str) -> str:
        if harness not in {"codex", "claude-code"} or kind not in {"sh", "ps1"}:
            raise ValueError("Unsupported installer")
        source = self._sources.read(kind).text
        configuration = self._configuration
        if kind == "sh":
            shebang, separator, body = source.partition("\n")
            if shebang != "#!/usr/bin/env bash" or not separator:
                raise ValueError("Invalid Bash installer source")
            arguments = [
                "--base-url", configuration.package_base_url,
                "--harness", harness, "--expected-endpoint", configuration.endpoint,
            ]
            if logs_endpoint:
                arguments.extend(("--logs-endpoint", logs_endpoint))
            return shebang + "\nset -- " + shlex.join(arguments) + "\n" + body
        return (
            "& {\n" + source + "\n} -BaseUrl " + powershell_literal(configuration.package_base_url)
            + " -Harness " + powershell_literal(harness)
            + " -ExpectedEndpoint " + powershell_literal(configuration.endpoint)
            + (" -LogsEndpoint " + powershell_literal(logs_endpoint) if logs_endpoint else "") + "\n"
        )
