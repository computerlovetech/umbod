from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, StringConstraints

ResourceText = Annotated[str, StringConstraints(min_length=1, max_length=262144, pattern=r"\S")]


class PackageResources(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill: ResourceText
    behaviour_skill: ResourceText
    license_text: ResourceText


class PackageResourceReader(Protocol):
    def read(self) -> PackageResources: ...


ScriptKind = Literal["sh", "ps1"]


class InstallerSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: ResourceText


class InstallerSourceReader(Protocol):
    def read(self, kind: ScriptKind) -> InstallerSource: ...
