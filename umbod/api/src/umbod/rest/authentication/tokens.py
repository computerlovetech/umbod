from collections.abc import Mapping


def extract_request_jwt_token(headers: Mapping[str, str], configured_header_name: str) -> str:
    header_value = headers.get(configured_header_name)
    if header_value is None:
        header_value = headers.get("Authorization", "")
    return extract_jwt_header_token(header_value)


def extract_jwt_header_token(header_value: str) -> str:
    stripped_value = header_value.strip()
    bearer_prefix = "Bearer "
    if stripped_value.lower().startswith(bearer_prefix.lower()):
        return stripped_value[len(bearer_prefix) :].strip()
    return stripped_value
