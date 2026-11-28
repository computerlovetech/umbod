from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, StringConstraints

from umbod.proxies import Model

ResourceText = Annotated[str, StringConstraints(min_length=1, max_length=262144, pattern=r"\S")]


class PackageResources(Model):
    model_config = ConfigDict(frozen=True)

    run_diagnostics_skill: ResourceText
    license_text: ResourceText


class PackageResourceReader(Protocol):
    def read(self) -> PackageResources: ...


ScriptKind = Literal["sh", "ps1"]


class InstallerSource(Model):
    model_config = ConfigDict(frozen=True)

    text: ResourceText


class InstallerSourceReader(Protocol):
    def read(self, kind: ScriptKind) -> InstallerSource: ...
