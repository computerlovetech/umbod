from typing import Protocol

from jwt import PyJWK


class SigningKeyResolver(Protocol):
    def resolve(self, token: str) -> PyJWK: ...


class SigningKeySetSource(Protocol):
    def fetch_keys(self) -> tuple[PyJWK, ...]: ...
