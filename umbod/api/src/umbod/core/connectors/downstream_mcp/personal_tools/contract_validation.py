import hashlib
import json

from jsonschema import Draft202012Validator
from referencing import Registry

from ..models import DiscoveredTool, ValidatedJsonObject
from .schema_validation import PersonalToolPolicyInvalid as PersonalToolPolicyInvalid, validate_contract_schema as validate_contract_schema


def contract_fingerprint(tool: DiscoveredTool) -> str:
    contract = {
        "name": tool.identity.downstream_name,
        "input_schema": tool.input_schema,
        "output_schema_status": tool.output_schema_status,
        "annotations": tool.annotations,
        "execution": tool.execution,
    }
    if tool.output_schema_status == "present":
        contract["output_schema"] = tool.output_schema
    return hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def validate_arguments(tool: DiscoveredTool, arguments: ValidatedJsonObject) -> None:
    validate_contract_schema(tool.input_schema)
    Draft202012Validator(tool.input_schema, registry=Registry()).validate(arguments)


def validate_output(tool: DiscoveredTool, output: ValidatedJsonObject) -> None:
    if tool.output_schema_status == "present":
        validate_contract_schema(tool.output_schema)
        Draft202012Validator(tool.output_schema, registry=Registry()).validate(output)
