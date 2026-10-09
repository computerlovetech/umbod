from collections.abc import Callable
from threading import Lock

import jwt
from jwt import PyJWK, PyJWKClient
from jwt.exceptions import InvalidTokenError, PyJWTError

from umbod.rest.authentication import JwtClaims, JwtVerificationError
from umbod.rest.users.signing_keys import SigningKeyResolver, SigningKeySetSource


class DisabledSigningKeyResolver:
    def resolve(self, token: str) -> PyJWK:
        raise JwtVerificationError("ID-token profiles are disabled")

    def clear(self) -> None:
        pass


class JwksSigningKeySetSource:
    def __init__(self, jwks_url: str, timeout_seconds: float) -> None:
        self.client = PyJWKClient(jwks_url, timeout=timeout_seconds)

    def fetch_keys(self) -> tuple[PyJWK, ...]:
        return tuple(self.client.get_signing_keys(refresh=True))


class CachedSigningKeyResolver:
    def __init__(
        self,
        source: SigningKeySetSource,
        clock: Callable[[], float],
        ttl_seconds: float,
        refresh_cooldown_seconds: float,
    ) -> None:
        if ttl_seconds <= 0 or refresh_cooldown_seconds <= 0:
            raise ValueError("JWKS cache intervals must be positive")
        self.source = source
        self.clock = clock
        self.ttl_seconds = ttl_seconds
        self.refresh_cooldown_seconds = refresh_cooldown_seconds
        self.lock = Lock()
        self.keys: tuple[PyJWK, ...] = ()
        self.expires_at = 0.0
        self.next_unknown_refresh_at = 0.0

    def resolve(self, token: str) -> PyJWK:
        try:
            key_id = jwt.get_unverified_header(token).get("kid")
        except InvalidTokenError as error:
            raise JwtVerificationError("Invalid profile token") from error
        if key_id is not None and not isinstance(key_id, str):
            raise JwtVerificationError("Invalid profile signing key identifier")
        with self.lock:
            now = self.clock()
            refreshed = False
            if now >= self.expires_at:
                self._refresh(now)
                refreshed = True
            matches = tuple(key for key in self.keys if key.key_id == key_id)
            if not matches and not refreshed and now >= self.next_unknown_refresh_at:
                self.next_unknown_refresh_at = now + self.refresh_cooldown_seconds
                self._refresh(now)
                matches = tuple(key for key in self.keys if key.key_id == key_id)
            if len(matches) != 1:
                raise JwtVerificationError("Profile signing key unavailable")
            return matches[0]

    def _refresh(self, now: float) -> None:
        self.expires_at = now + self.refresh_cooldown_seconds
        try:
            self.keys = self.source.fetch_keys()
        except (PyJWTError, ValueError) as error:
            self.keys = ()
            self.next_unknown_refresh_at = now + self.refresh_cooldown_seconds
            raise JwtVerificationError("Profile signing keys unavailable") from error
        self.expires_at = now + self.ttl_seconds

    def clear(self) -> None:
        with self.lock:
            self.keys = ()
            self.expires_at = 0.0
            self.next_unknown_refresh_at = 0.0


class JwksProfileJwtVerifier:
    def __init__(
        self, resolver: SigningKeyResolver, issuer: str, audience: str
    ) -> None:
        self.resolver = resolver
        self.issuer = issuer
        self.audience = audience

    def verify(self, token: str) -> JwtClaims:
        try:
            signing_key = self.resolver.resolve(token)
            if signing_key.algorithm_name != "RS256":
                raise JwtVerificationError("Unsupported profile signing algorithm")
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
        except (PyJWTError, TypeError, ValueError) as error:
            raise JwtVerificationError("Invalid profile token") from error
        return JwtClaims(claims=dict(claims))
