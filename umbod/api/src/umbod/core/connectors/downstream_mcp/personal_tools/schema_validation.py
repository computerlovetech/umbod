import json
from collections.abc import Iterator

from jsonschema import Draft202012Validator
from pydantic.types import JsonValue
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from ..models import ValidatedJsonObject


class PersonalToolPolicyInvalid(ValueError):
    pass


def _children(schema: dict[str, JsonValue]) -> Iterator[tuple[JsonValue, bool]]:
    for keyword in ("not", "if", "then", "else"):
        if keyword in schema:
            yield schema[keyword], True
    for keyword in ("additionalProperties", "unevaluatedProperties", "propertyNames", "items", "additionalItems", "contains", "unevaluatedItems", "contentSchema"):
        if keyword in schema:
            yield schema[keyword], False
    for keyword in ("allOf", "anyOf", "oneOf", "prefixItems"):
        value = schema.get(keyword)
        if isinstance(value, list):
            for child in value:
                yield child, keyword != "prefixItems"
    for keyword in ("properties", "patternProperties", "dependentSchemas", "$defs", "definitions"):
        value = schema.get(keyword)
        if isinstance(value, dict):
            for child in value.values():
                yield child, keyword == "dependentSchemas"


def _locations(schema: ValidatedJsonObject) -> tuple[dict[int, dict[str, JsonValue]], dict[int, set[int]]]:
    pending: list[tuple[JsonValue, int]] = [(schema, 0)]
    nodes: dict[int, dict[str, JsonValue]] = {}
    edges: dict[int, set[int]] = {}
    count = 0
    while pending:
        current, depth = pending.pop()
        count += 1
        if depth > 48 or count > 2048:
            raise PersonalToolPolicyInvalid("Schema exceeds complexity limit")
        if isinstance(current, bool):
            continue
        if not isinstance(current, dict):
            raise PersonalToolPolicyInvalid("Invalid subschema")
        nodes[id(current)] = current
        edges[id(current)] = set()
        for child, same_instance in _children(current):
            pending.append((child, depth + 1))
            if same_instance:
                edges[id(current)].add(id(child))
    return nodes, edges


def _keywords(nodes: dict[int, dict[str, JsonValue]]) -> None:
    anchors: dict[str, int] = {}
    for identity, schema in nodes.items():
        if "$schema" in schema and schema["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise PersonalToolPolicyInvalid("Unsupported schema dialect")
        if "$id" in schema or "$recursiveRef" in schema:
            raise PersonalToolPolicyInvalid("Unsupported schema identifier or reference")
        for keyword in ("$anchor", "$dynamicAnchor"):
            anchor = schema.get(keyword)
            if isinstance(anchor, str):
                if anchor in anchors and anchors[anchor] != identity:
                    raise PersonalToolPolicyInvalid("Ambiguous local anchor")
                anchors[anchor] = identity
        for keyword in ("$ref", "$dynamicRef"):
            if keyword in schema and (not isinstance(schema[keyword], str) or not schema[keyword].startswith("#")):
                raise PersonalToolPolicyInvalid("Only local schema references are supported")


def _references(schema: ValidatedJsonObject, nodes: dict[int, dict[str, JsonValue]], edges: dict[int, set[int]]) -> None:
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    resolver = Registry().with_resource("urn:umbod:personal-tool", resource).resolver("urn:umbod:personal-tool")
    for identity, current in nodes.items():
        for keyword in ("$ref", "$dynamicRef"):
            reference = current.get(keyword)
            if not isinstance(reference, str):
                continue
            target = resolver.lookup(reference).contents
            if not isinstance(target, bool) and id(target) not in nodes:
                raise PersonalToolPolicyInvalid("Reference does not target a subschema")
            edges[identity].add(id(target))


def _bounded_recursion(edges: dict[int, set[int]]) -> None:
    completed: set[int] = set()
    active: set[int] = set()
    for start in edges:
        pending = [(start, False)]
        while pending:
            current, exiting = pending.pop()
            if exiting:
                active.remove(current)
                completed.add(current)
                continue
            if current in active:
                raise PersonalToolPolicyInvalid("Schema recurses without descending into data")
            if current in completed:
                continue
            active.add(current)
            pending.append((current, True))
            pending.extend((child, False) for child in edges.get(current, ()))


def validate_contract_schema(schema: ValidatedJsonObject) -> None:
    try:
        if len(json.dumps(schema, allow_nan=False).encode()) > 65536:
            raise PersonalToolPolicyInvalid("Schema exceeds size limit")
        nodes, edges = _locations(schema)
        _keywords(nodes)
        Draft202012Validator.check_schema(schema)
        _references(schema, nodes, edges)
        _bounded_recursion(edges)
    except PersonalToolPolicyInvalid:
        raise
    except Exception:
        raise PersonalToolPolicyInvalid("Invalid or unresolved contract schema") from None
