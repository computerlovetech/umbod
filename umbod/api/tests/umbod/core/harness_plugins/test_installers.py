import base64
import json
import os
import shutil
import subprocess

import pytest

from umbod.core.harness_plugins.installers import HarnessInstallerService, InstallerConfiguration
from umbod.core.harness_plugins.ports import InstallerSource, ScriptKind
from umbod.core.harness_plugins.rendering import Harness


class InMemoryInstallerSourceReader:
    def __init__(self, source: str) -> None:
        self._source = InstallerSource(text=source)

    def read(self, kind: ScriptKind) -> InstallerSource:
        return self._source


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
@pytest.mark.parametrize("path", ["team+one", "team!one;v=2,@name:part&more=(yes)", "team'one", 'team"one', "team+ø", "team`one"])
def test_bash_binding_executes_exact_configured_values_and_discards_caller_arguments(
    harness: Harness, path: str,
) -> None:
    configuration = InstallerConfiguration(api_origin="https://api.example.test/", endpoint=f"https://mcp.example.test/{path}/")
    source = '#!/usr/bin/env bash\npython3 -c \'import json,sys; sys.stdout.write(json.dumps(sys.argv[1:]))\' "$@"\n'
    rendered = HarnessInstallerService(configuration, InMemoryInstallerSourceReader(source)).render(harness, "sh", "")
    result = subprocess.run(
        ["bash", "-s", "--", "--base-url", "https://attacker.test", "--harness", "unknown"],
        input=rendered, text=True, capture_output=True, check=True, timeout=10,
    )
    assert json.loads(result.stdout) == [
        "--base-url", "https://api.example.test/api/install/v1", "--harness", harness,
        "--expected-endpoint", f"https://mcp.example.test/{path}/mcp",
    ]
    assert rendered.split("\n", 2)[2] == source.split("\n", 1)[1]


def test_powershell_binding_wraps_entire_source_and_encodes_literal_arguments() -> None:
    configuration = InstallerConfiguration(api_origin="https://api.example.test", endpoint="https://mcp.example.test/team'one+ø;v=2/mcp")
    source = "[CmdletBinding()]\nparam([string]$BaseUrl, [string]$Harness, [string]$ExpectedEndpoint)\n$ExpectedEndpoint\n"
    rendered = HarnessInstallerService(configuration, InMemoryInstallerSourceReader(source)).render("claude-code", "ps1", "")
    assert rendered.startswith("& {\n" + source + "\n} -BaseUrl ")
    assert "team'one" not in rendered
    arguments = rendered.split("\n} -BaseUrl ", 1)[1].strip()
    encoded_values = [base64.b64encode(value.encode("utf-8")).decode("ascii") for value in (
        configuration.package_base_url, "claude-code", configuration.endpoint,
    )]
    expressions = ["([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + value + "')))" for value in encoded_values]
    assert arguments == expressions[0] + " -Harness " + expressions[1] + " -ExpectedEndpoint " + expressions[2]


@pytest.fixture
def powershell_command() -> list[str]:
    executable = shutil.which("pwsh") or shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if executable:
        return [executable]
    image = os.environ.get("UMBOD_TEST_POWERSHELL_DOCKER_IMAGE")
    if image:
        return ["docker", "run", "--rm", "--interactive", "--network", "none", "--pull=never", image, "pwsh"]
    pytest.skip("PowerShell execution requires native PowerShell or an explicitly configured local Docker image")


@pytest.mark.parametrize("endpoint", [
    "https://mcp.test/x’;Write-Output(123);‘/mcp",
    "https://mcp.test/x‘;Write-Output(456);’/mcp",
    "https://mcp.test/team'one+ø;v=2,@name:part&more=(yes)/mcp",
    'https://mcp.test/team“one”`two/mcp',
])
def test_powershell_binding_executes_exact_literal_values_without_injection(
    powershell_command: list[str], endpoint: str,
) -> None:
    configuration = InstallerConfiguration(api_origin="https://api.example.test", endpoint=endpoint)
    source = (
        "[CmdletBinding()]\nparam([string]$BaseUrl, [string]$Harness, [string]$ExpectedEndpoint)\n"
        "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
        "[Console]::Out.Write((@{BaseUrl=$BaseUrl; Harness=$Harness; ExpectedEndpoint=$ExpectedEndpoint;"
        " Marker='safe-marker'} | ConvertTo-Json -Compress))\n"
    )
    rendered = HarnessInstallerService(configuration, InMemoryInstallerSourceReader(source)).render("claude-code", "ps1", "")
    encoded_command = base64.b64encode(rendered.encode("utf-16le")).decode("ascii")
    result = subprocess.run(
        [*powershell_command, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded_command],
        capture_output=True, encoding="utf-8", check=True, timeout=30,
    )
    assert json.loads(result.stdout) == {
        "BaseUrl": "https://api.example.test/api/install/v1", "Harness": "claude-code",
        "ExpectedEndpoint": endpoint, "Marker": "safe-marker",
    }


@pytest.mark.parametrize("origin", [
    "", "https:///", "http://public.test", "https://user:secret@api.test", "https://api.test?", "https://api.test#",
    "https://api.test/path", "https://api.test:wrong", "https://api.test\n", "https://api.test\x7f",
    "https://api.test;touch", "https://api.test'", "https://api.test/$(touch)", "https://api.test\\evil",
])
def test_installer_configuration_rejects_nonliteral_or_nonorigin_api_urls(origin: str) -> None:
    with pytest.raises(ValueError):
        InstallerConfiguration(api_origin=origin, endpoint="https://mcp.test")


@pytest.mark.parametrize("endpoint", [
    "", "http://public.test", "https://user:secret@mcp.test", "https://mcp.test?secret=x", "https://mcp.test#x",
    "https://mcp.test/$(touch)", "https://mcp.test/${endpoint}", "https://mcp.test/\n", "https://mcp.test/\x7f",
    "https://mcp.test/%0a", "https://mcp.test\\evil", "https://mcp.test'evil/path",
])
def test_installer_configuration_rejects_unsafe_mcp_endpoints(endpoint: str) -> None:
    with pytest.raises(ValueError):
        InstallerConfiguration(api_origin="https://api.test", endpoint=endpoint)


def test_installer_configuration_normalizes_loopback_configuration() -> None:
    configuration = InstallerConfiguration(api_origin="http://127.0.0.1:18010/", endpoint="http://[::1]:8011/")
    assert configuration.package_base_url == "http://127.0.0.1:18010/api/install/v1"
    assert configuration.endpoint == "http://[::1]:8011/mcp"


@pytest.mark.parametrize("source", ["#!/bin/sh\nexit 0\n", "#!/usr/bin/env bash"])
def test_bash_binding_rejects_invalid_script_resources(source: str) -> None:
    configuration = InstallerConfiguration(api_origin="https://api.test", endpoint="https://mcp.test")
    with pytest.raises(ValueError):
        HarnessInstallerService(configuration, InMemoryInstallerSourceReader(source)).render("codex", "sh", "")
