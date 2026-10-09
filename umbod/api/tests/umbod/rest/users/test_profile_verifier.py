import json

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt import PyJWK
from jwt.exceptions import InvalidKeyError, PyJWTError

from umbod.rest.authentication import JwtVerificationError, JwtVerifier
from umbod.rest.users.jwks import JwksProfileJwtVerifier
from umbod.rest.users.signing_keys import SigningKeyResolver


class InMemorySigningKeyResolver:
    def __init__(self, key: PyJWK) -> None:
        self.key = key

    def resolve(self, token: str) -> PyJWK:
        return self.key


@pytest.mark.parametrize("algorithm", ["ES256", "HS256", "RS512"])
def test_profile_verifier_rejects_non_rs256_key_algorithm(algorithm: str) -> None:
    if algorithm == "ES256":
        private = ec.generate_private_key(ec.SECP256R1())
        raw = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    elif algorithm == "HS256":
        raw = json.loads(
            jwt.algorithms.HMACAlgorithm.to_jwk(b"unused-signing-key-at-least-32-bytes")
        )
    else:
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        raw = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    resolver: SigningKeyResolver = InMemorySigningKeyResolver(
        PyJWK({**raw, "alg": algorithm})
    )
    verifier: JwtVerifier = JwksProfileJwtVerifier(
        resolver, "https://issuer.test/", "web"
    )
    with pytest.raises(
        JwtVerificationError, match="Unsupported profile signing algorithm"
    ):
        verifier.verify("unused-token")


@pytest.mark.parametrize(
    "error",
    [
        InvalidKeyError("private-key-error"),
        TypeError("private-key-error"),
        ValueError("private-key-error"),
    ],
)
def test_profile_verifier_normalizes_expected_key_decode_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: PyJWTError | TypeError | ValueError,
) -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key = PyJWK(json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())))
    resolver: SigningKeyResolver = InMemorySigningKeyResolver(key)
    verifier: JwtVerifier = JwksProfileJwtVerifier(
        resolver, "https://issuer.test/", "web"
    )

    def invalid_decode(*args: object, **kwargs: object) -> dict[str, object]:
        raise error

    monkeypatch.setattr(jwt, "decode", invalid_decode)
    with pytest.raises(JwtVerificationError, match="Invalid profile token"):
        verifier.verify("unused-token")
