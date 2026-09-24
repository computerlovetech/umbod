def extract_jwt_header_token(header_value: str) -> str:
    stripped_value = header_value.strip()
    bearer_prefix = "Bearer "
    if stripped_value.lower().startswith(bearer_prefix.lower()):
        return stripped_value[len(bearer_prefix) :].strip()
    return stripped_value
