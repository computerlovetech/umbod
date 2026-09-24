import base64
import hashlib
import hmac

_DERIVATION_SALT = b"umbod-root-secret-v1"


def derive_secret(root_secret: str, purpose: str) -> str:
    pseudorandom_key = hmac.new(
        _DERIVATION_SALT,
        root_secret.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    derived_key = hmac.new(
        pseudorandom_key,
        f"umbod:{purpose}".encode("utf-8") + b"\x01",
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(derived_key).decode("ascii")


__all__ = ["derive_secret"]
