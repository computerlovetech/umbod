def contains_secret(value: object, secret: str) -> bool:
    if isinstance(value, str):
        return secret in value
    if isinstance(value, dict):
        return any(contains_secret(key, secret) or contains_secret(item, secret) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(contains_secret(item, secret) for item in value)
    return False
