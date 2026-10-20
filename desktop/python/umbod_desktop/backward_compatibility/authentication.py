import hashlib
import secrets


class LegacyAgentCredentials:
    def __init__(self, hashes: tuple[str, ...]) -> None:
        self.hashes = hashes

    def __call__(self, token: str) -> bool:
        digest = hashlib.sha256(token.encode()).hexdigest()
        return any(secrets.compare_digest(digest, saved) for saved in self.hashes)
