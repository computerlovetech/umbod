from __future__ import annotations

from typing import Annotated, Literal, TypeAlias, Union

from pydantic import ConfigDict, Field, JsonValue

from umbod.proxies import Model


class OpenApiMetadata(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str
    version: str
    description: str


class PrimitiveSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["string", "integer", "number", "boolean"]
    format: str
    description: str
    enum: tuple[JsonValue, ...] = Field(default=(), exclude_if=lambda values: not values)


class ArraySchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["array"] = "array"
    items: "OpenApiSchema"
    description: str


class ObjectSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["object"] = "object"
    properties: dict[str, "OpenApiSchema"]
    required: tuple[str, ...]
    description: str
    additional_properties: Union[bool, "OpenApiSchema"] = True


class NullSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["null"] = "null"
    description: str


class BooleanSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["boolean_schema"] = "boolean_schema"
    allows_values: bool
    description: str = ""


class CompositionSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["composition"] = "composition"
    operator: Literal["oneOf", "anyOf", "allOf", "not"]
    schemas: tuple["OpenApiSchema", ...]
    description: str


class UnspecifiedSchema(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["unspecified"] = "unspecified"
    description: str


OpenApiSchema: TypeAlias = Annotated[
    PrimitiveSchema
    | ArraySchema
    | ObjectSchema
    | NullSchema
    | BooleanSchema
    | CompositionSchema
    | UnspecifiedSchema,
    Field(discriminator="type"),
]


class OpenApiParameter(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    location: Literal["path", "query", "header"]
    required: bool
    description: str
    style: Literal["simple", "form", "spaceDelimited", "pipeDelimited", "deepObject"]
    explode: bool
    capability_schema: OpenApiSchema


class OpenApiRequestBody(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    media_type: Literal["application/json"]
    required: bool
    description: str
    capability_schema: OpenApiSchema


class OpenApiResponseBody(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status_code: str
    media_type: str
    description: str
    capability_schema: OpenApiSchema


class OpenApiEndpointCapability(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_id: str
    method: Literal["get", "put", "post", "delete", "options", "head", "patch", "trace"]
    path: str
    summary: str
    description: str
    parameters: tuple[OpenApiParameter, ...]
    request_bodies: tuple[OpenApiRequestBody, ...]
    response_bodies: tuple[OpenApiResponseBody, ...]


class ImportedOpenApiCandidate(Model):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: OpenApiMetadata
    server_candidates: tuple[str, ...]
    endpoints: tuple[OpenApiEndpointCapability, ...]
