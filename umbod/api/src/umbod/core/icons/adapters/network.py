from urllib.parse import SplitResult, unquote, urlsplit


def validate_favicon_url(value: str) -> SplitResult:
    parts = urlsplit(value)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.fragment
        or "\\" in value
        or "%" in parts.netloc
        or parts.port == 0
        or any(ord(character) <= 32 or ord(character) >= 127 for character in value)
        or any(ord(character) < 32 or ord(character) == 127 for character in unquote(value))
    ):
        raise ValueError("Invalid favicon destination")
    return parts
