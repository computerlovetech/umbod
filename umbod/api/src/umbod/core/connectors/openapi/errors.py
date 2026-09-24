from typing import TypeAlias

from pydantic import ConfigDict

from umbod.proxies import Model

OpenApiIssueLocationPart: TypeAlias = str | int


class OpenApiValidationIssue(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    location: tuple[OpenApiIssueLocationPart, ...]
    message: str


class OpenApiCandidateValidationError(ValueError):
    issues: tuple[OpenApiValidationIssue, ...]

    def __init__(self, issues: tuple[OpenApiValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("OpenAPI candidate validation failed")


class OpenApiPermissionGrantConflict(ValueError):
    def __init__(
        self,
        connector_id: str,
        removed_operation_ids: tuple[str, ...],
        affected_group_ids: tuple[str, ...],
    ) -> None:
        self.connector_id = connector_id
        self.removed_operation_ids = removed_operation_ids
        self.affected_group_ids = affected_group_ids
        super().__init__("Active permission grants prevent removing OpenAPI operations")
