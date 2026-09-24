from typing import Protocol

from umbod.core.configuration.persistence.crypto import _decrypt, _encrypt


class TextCipher(Protocol):
    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, ciphertext: str) -> str: ...


class AuthenticatedTextCipher:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    def encrypt(self, plaintext: str) -> str:
        return _encrypt(plaintext, self._secret)

    def decrypt(self, ciphertext: str) -> str:
        return _decrypt(ciphertext, self._secret)
