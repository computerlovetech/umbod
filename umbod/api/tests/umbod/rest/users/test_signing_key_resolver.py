import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from urllib.error import URLError
from urllib.request import Request

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.exceptions import PyJWKClientError

from umbod.rest.authentication import JwtVerificationError
from umbod.rest.users.jwks import CachedSigningKeyResolver, JwksSigningKeySetSource
from umbod.rest.users.signing_keys import SigningKeyResolver, SigningKeySetSource


class Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


class InMemoryKeySetSource:
    def __init__(self, keys: tuple[PyJWK, ...]) -> None:
        self.keys = keys
        self.fetch_count = 0
        self.fail = False
        self.started = Event()
        self.release = Event()
        self.release.set()

    def fetch_keys(self) -> tuple[PyJWK, ...]:
        self.fetch_count += 1
        self.started.set()
        if not self.release.wait(timeout=3):
            raise TimeoutError("Test key source was not released")
        if self.fail:
            raise PyJWKClientError("Unavailable key source")
        return self.keys


@pytest.fixture
def key() -> PyJWK:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return PyJWK(
        {
            **json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())),
            "kid": "known",
        }
    )


def token(kid: str) -> str:
    return jwt.encode(
        {},
        "unused-signing-key-at-least-32-bytes",
        algorithm="HS256",
        headers={"kid": kid},
    )


def test_resolver_refreshes_expired_keys(key: PyJWK) -> None:
    source = InMemoryKeySetSource((key,))
    clock = Clock(100.0)
    resolver: SigningKeyResolver = CachedSigningKeyResolver(source, clock, 300.0, 5.0)
    assert resolver.resolve(token("known")) == key
    clock.now = 399.0
    assert resolver.resolve(token("known")) == key
    assert source.fetch_count == 1
    clock.now = 400.0
    assert resolver.resolve(token("known")) == key
    assert source.fetch_count == 2


def test_unknown_key_refreshes_are_rate_bounded(key: PyJWK) -> None:
    source = InMemoryKeySetSource((key,))
    clock = Clock(100.0)
    resolver: SigningKeyResolver = CachedSigningKeyResolver(source, clock, 300.0, 5.0)
    resolver.resolve(token("known"))
    for kid in ("missing-one", "missing-two", "missing-three"):
        with pytest.raises(JwtVerificationError):
            resolver.resolve(token(kid))
    assert source.fetch_count == 2
    clock.now = 105.0
    with pytest.raises(JwtVerificationError):
        resolver.resolve(token("missing-four"))
    assert source.fetch_count == 3


def test_failed_fetches_have_short_retry_cooldown(key: PyJWK) -> None:
    source = InMemoryKeySetSource((key,))
    source.fail = True
    clock = Clock(100.0)
    resolver: SigningKeyResolver = CachedSigningKeyResolver(source, clock, 300.0, 5.0)
    for _ in range(3):
        with pytest.raises(JwtVerificationError):
            resolver.resolve(token("known"))
    assert source.fetch_count == 1
    source.fail = False
    clock.now = 105.0
    assert resolver.resolve(token("known")) == key
    assert source.fetch_count == 2


def test_concurrent_cache_misses_share_single_fetch(key: PyJWK) -> None:
    source = InMemoryKeySetSource((key,))
    source.release.clear()
    resolver: SigningKeyResolver = CachedSigningKeyResolver(
        source, Clock(100.0), 300.0, 5.0
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        lookups = [executor.submit(resolver.resolve, token("known")) for _ in range(8)]
        try:
            assert source.started.wait(timeout=1)
        finally:
            source.release.set()
        assert [lookup.result(timeout=2) for lookup in lookups] == [key] * 8
    assert source.fetch_count == 1


def test_jwks_source_uses_bounded_fetch_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timeouts: list[float] = []

    def unavailable(url: Request, timeout: float, context: object) -> object:
        timeouts.append(timeout)
        raise URLError("Unavailable")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)
    source: SigningKeySetSource = JwksSigningKeySetSource(
        "https://identity.test/jwks", 3.0
    )
    with pytest.raises(PyJWKClientError):
        source.fetch_keys()
    assert timeouts == [3.0]
