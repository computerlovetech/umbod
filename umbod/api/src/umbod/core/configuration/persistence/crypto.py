import base64
import hashlib
import hmac
import json
import secrets

from pydantic import SecretStr
from umbod.proxies import Model

from umbod.core.configuration.exceptions import (
    ConnectorConfigurationDecryptionError,
)


def _configuration_plain_json(configuration: Model) -> str:
    return json.dumps(_plain_secret_values(configuration.model_dump(mode="python")))


def _plain_secret_values(value: object) -> object:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if isinstance(value, dict):
        return {key: _plain_secret_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_secret_values(item) for item in value]
    return value


def _encrypt(plaintext: str, secret: str) -> str:
    nonce = secrets.token_bytes(16)
    plaintext_bytes = plaintext.encode("utf-8")
    ciphertext = _xor_with_keystream(plaintext_bytes, secret, nonce)
    version = b"v1"
    tag = _tag(secret, version + nonce + ciphertext)
    envelope = version + nonce + tag + ciphertext
    return base64.urlsafe_b64encode(envelope).decode("ascii")


def _decrypt(ciphertext: str, secret: str) -> str:
    try:
        envelope = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    except ValueError as error:
        raise ConnectorConfigurationDecryptionError() from error
    if len(envelope) < 50:
        raise ConnectorConfigurationDecryptionError()
    version = envelope[:2]
    nonce = envelope[2:18]
    expected_tag = envelope[18:50]
    encrypted_payload = envelope[50:]
    if version != b"v1":
        raise ConnectorConfigurationDecryptionError()
    actual_tag = _tag(secret, version + nonce + encrypted_payload)
    if not hmac.compare_digest(expected_tag, actual_tag):
        raise ConnectorConfigurationDecryptionError()
    plaintext = _xor_with_keystream(encrypted_payload, secret, nonce)
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConnectorConfigurationDecryptionError() from error


def _xor_with_keystream(payload: bytes, secret: str, nonce: bytes) -> bytes:
    keystream = bytearray()
    counter = 0
    secret_bytes = secret.encode("utf-8")
    while len(keystream) < len(payload):
        counter_bytes = counter.to_bytes(8, "big")
        keystream.extend(hmac.new(secret_bytes, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(value ^ keystream[index] for index, value in enumerate(payload))


def _tag(secret: str, authenticated_data: bytes) -> bytes:
    return hmac.new(
        secret.encode("utf-8"),
        authenticated_data,
        hashlib.sha256,
    ).digest()
