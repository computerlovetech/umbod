from pydantic import BaseModel, ConfigDict


class InitRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_directory: str
    name: str
    module: str


class ProjectSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    metadata: bytes


class InitPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    request: InitRequest
    original_metadata: bytes
    metadata_addition: bytes
    source: str
    module_path: str
    metadata_path: str
