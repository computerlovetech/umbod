from collections.abc import Mapping
from typing import Literal, TypeAlias, cast

from pydantic import ConfigDict, ValidationError

from umbod.proxies import Model

from umbod.core.connectors.openapi.errors import (
    OpenApiCandidateValidationError,
    OpenApiValidationIssue,
)
from umbod.core.connectors.openapi.importing.json_pointer import (
    JsonPointerResolutionError,
    SameDocumentJsonPointerResolver,
)
from umbod.core.connectors.openapi.models import (
    ImportedOpenApiCandidate,
    OpenApiEndpointCapability,
    OpenApiMetadata,
    OpenApiParameter,
    OpenApiRequestBody,
    OpenApiResponseBody,
    OpenApiSchema,
)
from umbod.core.connectors.openapi.importing.parameter_parser import OpenApiParameterDefinitionParser
from umbod.core.connectors.openapi.importing.parsing import ValidationIssues
from umbod.core.connectors.openapi.importing.schema_parser import OpenApiSchemaParser
from umbod.core.connectors.openapi.importing.server_parser import OpenApiServerParser

Location: TypeAlias = tuple[str | int, ...]
HttpMethod: TypeAlias = Literal["get", "put", "post", "delete", "options", "head", "patch", "trace"]
HTTP_METHODS: tuple[HttpMethod, ...] = (
    "get",
    "put",
    "post",
    "delete",
    "options",
    "head",
    "patch",
    "trace",
)


class OpenApiCandidateDto(Model):
    model_config = ConfigDict(extra="allow")

    openapi: object
    info: object
    paths: object
    servers: object = []


class InMemoryOpenApiCandidateImporter:
    def import_candidate(self, candidate: object) -> ImportedOpenApiCandidate:
        self._resolver = SameDocumentJsonPointerResolver(candidate, maximum_depth=64)
        try:
            dto = OpenApiCandidateDto.model_validate(candidate)
        except ValidationError as error:
            issues = self._candidate_dto_issues(candidate, error)
            raise OpenApiCandidateValidationError(issues) from error

        issues: list[OpenApiValidationIssue] = []
        self._validate_version(dto.openapi, issues)
        metadata = self._parse_metadata(dto.info, issues)
        servers = self._parse_servers(dto.servers, issues)
        endpoints = self._parse_paths(dto.paths, issues)
        self._validate_unique_operation_ids(dto.paths, issues)
        if issues:
            raise OpenApiCandidateValidationError(tuple(issues))
        if metadata is None:
            raise OpenApiCandidateValidationError(
                (self._issue("invalid_info", ("info",), "Info must be an object"),)
            )
        return ImportedOpenApiCandidate(
            metadata=metadata, server_candidates=tuple(servers), endpoints=tuple(endpoints)
        )

    def _candidate_dto_issues(
        self, candidate: object, error: ValidationError
    ) -> tuple[OpenApiValidationIssue, ...]:
        if not isinstance(candidate, Mapping):
            return (self._issue("invalid_candidate", (), "Candidate must be an object"),)
        issues: list[OpenApiValidationIssue] = []
        for detail in error.errors():
            location = cast(Location, tuple(detail["loc"]))
            if location == ("openapi",):
                issues.append(
                    self._issue("missing_openapi_version", location, "OpenAPI version is required")
                )
            elif location == ("info",):
                issues.append(self._issue("missing_info", location, "Info is required"))
            elif location == ("paths",):
                issues.append(self._issue("missing_paths", location, "Paths are required"))
            else:
                issues.append(
                    self._issue(
                        "invalid_candidate", location, "Candidate contains unsupported fields"
                    )
                )
        return tuple(issues)

    def _validate_version(self, version: object, issues: list[OpenApiValidationIssue]) -> None:
        if not isinstance(version, str) or not (
            version.startswith("3.0.") or version.startswith("3.1.")
        ):
            issues.append(
                self._issue(
                    "unsupported_openapi_version",
                    ("openapi",),
                    "Only OpenAPI 3.0.x and 3.1.x are supported",
                )
            )

    def _parse_metadata(
        self, raw_info: object, issues: list[OpenApiValidationIssue]
    ) -> OpenApiMetadata | None:
        if not isinstance(raw_info, Mapping):
            issues.append(self._issue("invalid_info", ("info",), "Info must be an object"))
            return None
        title = raw_info.get("title")
        version = raw_info.get("version")
        description = raw_info.get("description", "")
        valid = True
        if not isinstance(title, str) or not title:
            issues.append(
                self._issue(
                    "invalid_info", ("info", "title"), "Info title must be a non-empty string"
                )
            )
            valid = False
        if not isinstance(version, str) or not version:
            issues.append(
                self._issue(
                    "invalid_info", ("info", "version"), "Info version must be a non-empty string"
                )
            )
            valid = False
        if not isinstance(description, str):
            issues.append(
                self._issue(
                    "invalid_info", ("info", "description"), "Info description must be a string"
                )
            )
            valid = False
        if not valid:
            return None
        return OpenApiMetadata(
            title=cast(str, title), version=cast(str, version), description=cast(str, description)
        )

    def _parse_servers(
        self, raw_servers: object, issues: list[OpenApiValidationIssue]
    ) -> list[str]:
        collector = ValidationIssues()
        servers = OpenApiServerParser(collector).parse(raw_servers, ("servers",))
        issues.extend(collector.values)
        return servers

    def _parse_paths(
        self, raw_paths: object, issues: list[OpenApiValidationIssue]
    ) -> list[OpenApiEndpointCapability]:
        if not isinstance(raw_paths, Mapping):
            issues.append(self._issue("invalid_paths", ("paths",), "Paths must be an object"))
            return []
        endpoints: list[OpenApiEndpointCapability] = []
        for path in sorted(raw_paths, key=str):
            raw_path_item = raw_paths[path]
            path_location: Location = ("paths", cast(str, path))
            raw_path_item = self._resolve_object(raw_path_item, path_location, issues)
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or not isinstance(raw_path_item, Mapping)
            ):
                issues.append(
                    self._issue(
                        "invalid_path_item",
                        path_location,
                        "Path item must be an object at an absolute path",
                    )
                )
                continue
            if "servers" in raw_path_item:
                issues.append(
                    self._issue(
                        "unsupported_server_override",
                        (*path_location, "servers"),
                        "Server overrides are unsupported",
                    )
                )
            path_parameters = self._parse_parameters(
                raw_path_item.get("parameters", []), (*path_location, "parameters"), issues
            )
            for method in HTTP_METHODS:
                if method not in raw_path_item:
                    continue
                endpoint = self._parse_operation(
                    path, method, raw_path_item[method], path_parameters, issues
                )
                if endpoint is not None:
                    endpoints.append(endpoint)
        endpoints.sort(key=lambda endpoint: (endpoint.path, HTTP_METHODS.index(endpoint.method)))
        return endpoints

    def _parse_operation(
        self,
        path: str,
        method: HttpMethod,
        raw_operation: object,
        path_parameters: list[OpenApiParameter],
        issues: list[OpenApiValidationIssue],
    ) -> OpenApiEndpointCapability | None:
        location: Location = ("paths", path, method)
        if not isinstance(raw_operation, Mapping):
            issues.append(self._issue("invalid_operation", location, "Operation must be an object"))
            return None
        if "$ref" in raw_operation:
            issues.append(
                self._issue(
                    "unsupported_reference", (*location, "$ref"), "References are unsupported"
                )
            )
        if "servers" in raw_operation:
            issues.append(
                self._issue(
                    "unsupported_server_override",
                    (*location, "servers"),
                    "Server overrides are unsupported",
                )
            )
        operation_id = raw_operation.get("operationId")
        if not isinstance(operation_id, str) or not operation_id:
            issues.append(
                self._issue(
                    "missing_operation_id", (*location, "operationId"), "Operation ID is required"
                )
            )
            return None
        summary = raw_operation.get("summary", "")
        description = raw_operation.get("description", "")
        if not isinstance(summary, str) or not isinstance(description, str):
            issues.append(
                self._issue(
                    "invalid_operation", location, "Summary and description must be strings"
                )
            )
            return None
        operation_parameters = self._parse_parameters(
            raw_operation.get("parameters", []), (*location, "parameters"), issues
        )
        merged = {(parameter.name, parameter.location): parameter for parameter in path_parameters}
        merged.update(
            {(parameter.name, parameter.location): parameter for parameter in operation_parameters}
        )
        request_bodies = self._parse_request_body(
            raw_operation.get("requestBody"), (*location, "requestBody"), issues
        )
        responses = self._parse_responses(
            raw_operation.get("responses"), (*location, "responses"), issues
        )
        return OpenApiEndpointCapability(
            operation_id=operation_id,
            method=method,
            path=path,
            summary=summary,
            description=description,
            parameters=tuple(merged.values()),
            request_bodies=tuple(request_bodies),
            response_bodies=tuple(responses),
        )

    def _parse_parameters(
        self, raw_parameters: object, location: Location, issues: list[OpenApiValidationIssue]
    ) -> list[OpenApiParameter]:
        if isinstance(raw_parameters, list):
            raw_parameters = [
                self._resolve_object(parameter, (*location, index), issues)
                for index, parameter in enumerate(raw_parameters)
            ]
        return OpenApiParameterDefinitionParser(self._parse_schema).parse(
            raw_parameters, location, issues
        )

    def _parse_request_body(
        self, raw_body: object, location: Location, issues: list[OpenApiValidationIssue]
    ) -> list[OpenApiRequestBody]:
        if raw_body is None:
            return []
        if not isinstance(raw_body, Mapping):
            issues.append(
                self._issue("invalid_request_body", location, "Request body must be an object")
            )
            return []
        raw_body = self._resolve_object(raw_body, location, issues)
        if not isinstance(raw_body, Mapping):
            return []
        required = raw_body.get("required", False)
        description = raw_body.get("description", "")
        content = raw_body.get("content", {})
        if (
            not isinstance(required, bool)
            or not isinstance(description, str)
            or not isinstance(content, Mapping)
        ):
            issues.append(
                self._issue("invalid_request_body", location, "Request body attributes are invalid")
            )
            return []
        media = content.get("application/json")
        if media is None:
            return []
        schema = self._parse_media_schema(media, (*location, "content", "application/json"), issues)
        if schema is None:
            return []
        return [
            OpenApiRequestBody(
                media_type="application/json",
                required=required,
                description=description,
                capability_schema=schema,
            )
        ]

    def _parse_responses(
        self, raw_responses: object, location: Location, issues: list[OpenApiValidationIssue]
    ) -> list[OpenApiResponseBody]:
        if not isinstance(raw_responses, Mapping):
            issues.append(self._issue("invalid_responses", location, "Responses must be an object"))
            return []
        if "$ref" in raw_responses:
            issues.append(
                self._issue(
                    "unsupported_reference", (*location, "$ref"), "References are unsupported"
                )
            )
            return []
        bodies: list[OpenApiResponseBody] = []
        for status_code in sorted(raw_responses, key=str):
            response = raw_responses[status_code]
            item_location = (*location, cast(str, status_code))
            response = self._resolve_object(response, item_location, issues)
            if not isinstance(status_code, str) or not isinstance(response, Mapping):
                issues.append(
                    self._issue("invalid_response", item_location, "Response must be an object")
                )
                continue
            description = response.get("description")
            content = response.get("content", {})
            if not isinstance(description, str) or not isinstance(content, Mapping):
                issues.append(
                    self._issue(
                        "invalid_response", item_location, "Response attributes are invalid"
                    )
                )
                continue
            json_media_types = sorted(
                media_type
                for media_type in content
                if isinstance(media_type, str)
                and (media_type == "application/json" or media_type.startswith("application/") and media_type.endswith("+json"))
            )
            if "application/json" in json_media_types:
                json_media_types.remove("application/json")
                json_media_types.insert(0, "application/json")
            for media_type in json_media_types:
                schema = self._parse_media_schema(
                    content[media_type], (*item_location, "content", media_type), issues
                )
                if schema is not None:
                    bodies.append(
                        OpenApiResponseBody(
                            status_code=status_code,
                            media_type=media_type,
                            description=description,
                            capability_schema=schema,
                        )
                    )
        return bodies

    def _parse_media_schema(
        self, raw_media: object, location: Location, issues: list[OpenApiValidationIssue]
    ) -> OpenApiSchema | None:
        if not isinstance(raw_media, Mapping):
            issues.append(
                self._issue("invalid_media_type", location, "Media type must be an object")
            )
            return None
        raw_media = self._resolve_object(raw_media, location, issues)
        if not isinstance(raw_media, Mapping) or "schema" not in raw_media:
            return None
        return self._parse_schema(raw_media["schema"], (*location, "schema"), issues)

    def _parse_schema(
        self, raw_schema: object, location: Location, issues: list[OpenApiValidationIssue]
    ) -> OpenApiSchema | None:
        collector = ValidationIssues()
        parsed = OpenApiSchemaParser(collector, self._resolver.resolve).parse(raw_schema, location)
        issues.extend(collector.values)
        return parsed

    def _resolve_object(
        self,
        raw: object,
        location: Location,
        issues: list[OpenApiValidationIssue],
    ) -> object:
        if not isinstance(raw, Mapping) or "$ref" not in raw:
            return raw
        reference = raw.get("$ref")
        if not isinstance(reference, str):
            issues.append(
                self._issue("invalid_reference", (*location, "$ref"), "Reference must be a string")
            )
            return raw
        try:
            resolved = self._resolver.resolve(reference)
        except JsonPointerResolutionError as error:
            issues.append(self._issue("unsupported_reference", (*location, "$ref"), str(error)))
            return raw
        if not isinstance(resolved, Mapping):
            issues.append(
                self._issue(
                    "invalid_reference", (*location, "$ref"), "Reference target must be an object"
                )
            )
            return raw
        return {**resolved, **{key: value for key, value in raw.items() if key != "$ref"}}

    def _validate_unique_operation_ids(
        self, raw_paths: object, issues: list[OpenApiValidationIssue]
    ) -> None:
        if not isinstance(raw_paths, Mapping):
            return
        seen: set[str] = set()
        for path in sorted(raw_paths, key=str):
            path_item = raw_paths[path]
            if not isinstance(path, str) or not isinstance(path_item, Mapping):
                continue
            for method in HTTP_METHODS:
                operation = path_item.get(method)
                if not isinstance(operation, Mapping):
                    continue
                operation_id = operation.get("operationId")
                if not isinstance(operation_id, str) or not operation_id:
                    continue
                location: Location = ("paths", path, method, "operationId")
                if operation_id in seen:
                    issues.append(
                        self._issue(
                            "duplicate_operation_id", location, "Operation ID must be unique"
                        )
                    )
                else:
                    seen.add(operation_id)

    def _issue(self, code: str, location: Location, message: str) -> OpenApiValidationIssue:
        return OpenApiValidationIssue(code=code, location=location, message=message)
