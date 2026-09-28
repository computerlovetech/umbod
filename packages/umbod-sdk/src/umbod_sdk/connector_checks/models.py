from pydantic import BaseModel, ConfigDict


class MetadataRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_directory: str


class MetadataContent(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry_names: tuple[str, ...]
