import re
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from umbod.core.capabilities.descriptions import CapabilityDescription


_IDENTIFIER_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


class ConnectorToolSearchCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    description: str
    connector_id: str
    connector_display_name: str = Field(default="", exclude=True)
    connector_capability_description: CapabilityDescription = Field(
        default="Connector capabilities", exclude=True
    )
    operation_name: str
    input_schema: dict[str, Any]
    search_hints: tuple[str, ...] = Field(default=(), exclude=True)

    @model_validator(mode="before")
    @classmethod
    def default_connector_display_name(cls, data: Any) -> Any:
        if isinstance(data, dict) and not data.get("connector_display_name"):
            return {**data, "connector_display_name": data.get("connector_id", "")}
        return data


class ConnectorToolSearchInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=50)
    connector_ids: tuple[str, ...] = ()
    candidates: list[ConnectorToolSearchCandidate]


class ConnectorToolSearchMatch(ConnectorToolSearchCandidate):
    relevance_score: float


class ConnectorToolSearchOutput(BaseModel):
    matches: list[ConnectorToolSearchMatch]


class ConnectorToolSearch(Protocol):
    def search(self, search_input: ConnectorToolSearchInput) -> ConnectorToolSearchOutput: ...


class InMemoryFuzzyConnectorToolSearch:
    def search(self, search_input: ConnectorToolSearchInput) -> ConnectorToolSearchOutput:
        query = _normalize(search_input.query)
        query_terms = frozenset(query.split())
        matches: list[ConnectorToolSearchMatch] = []
        connector_scope = frozenset(search_input.connector_ids)
        for candidate in search_input.candidates:
            if connector_scope and candidate.connector_id not in connector_scope:
                continue
            score = _candidate_score(candidate, query, query_terms)
            if score == 0:
                continue
            matches.append(_match(candidate, score))
        matches.sort(
            key=lambda match: (
                -match.relevance_score,
                match.tool_name,
                match.connector_id,
                match.operation_name,
            )
        )
        return ConnectorToolSearchOutput(matches=matches[: search_input.limit])


def _candidate_score(
    candidate: ConnectorToolSearchCandidate,
    query: str,
    query_terms: frozenset[str],
) -> float:
    weighted_fields = (
        (candidate.connector_display_name, 12.0),
        (candidate.connector_id, 11.0),
        (candidate.connector_capability_description, 10.5),
        (candidate.operation_name, 10.0),
        (candidate.tool_name, 6.0),
        (*candidate.search_hints, 8.0),
        (candidate.description, 3.0),
        (*_schema_property_names(candidate.input_schema), 0.5),
    )
    return round(
        sum(
            _field_score(value, weight, query, query_terms)
            for *values, weight in weighted_fields
            for value in values
        ),
        6,
    )


def _field_score(value: str, weight: float, query: str, query_terms: frozenset[str]) -> float:
    normalized = _normalize(value)
    if not normalized:
        return 0.0
    field_terms = frozenset(normalized.split())
    matched = len(query_terms & field_terms)
    if matched == 0 and query not in normalized:
        return 0.0
    score = weight * matched / len(query_terms)
    if normalized == query:
        score += weight
    elif query in normalized:
        score += weight * 0.25
    return score


def _normalize(value: str) -> str:
    separated = _IDENTIFIER_BOUNDARY.sub(" ", value)
    return _NON_ALPHANUMERIC.sub(" ", separated.casefold()).strip()


def _schema_property_names(schema: Any) -> tuple[str, ...]:
    names: list[str] = []
    if isinstance(schema, dict):
        properties = schema.get("properties")
        if isinstance(properties, dict):
            names.extend(str(name) for name in properties)
        for value in schema.values():
            names.extend(_schema_property_names(value))
    elif isinstance(schema, list):
        for value in schema:
            names.extend(_schema_property_names(value))
    return tuple(names)


def _match(
    candidate: ConnectorToolSearchCandidate, relevance_score: float
) -> ConnectorToolSearchMatch:
    return ConnectorToolSearchMatch(
        tool_name=candidate.tool_name,
        description=candidate.description,
        connector_id=candidate.connector_id,
        connector_display_name=candidate.connector_display_name,
        connector_capability_description=candidate.connector_capability_description,
        operation_name=candidate.operation_name,
        input_schema=candidate.input_schema,
        search_hints=candidate.search_hints,
        relevance_score=relevance_score,
    )
