import pytest
from pydantic import ValidationError

from umbod.config import AppConfig


@pytest.mark.parametrize("origin", [
    "https://admin.example",
    "https://admin.example:8443/",
    "http://localhost:3010",
    "http://127.0.0.1:3010/",
    "http://[::1]:3010",
])
def test_public_site_origin_accepts_secure_or_loopback_origins(origin: str) -> None:
    settings = AppConfig(endpoints={"site_base_url": origin})
    assert settings.endpoints.site_base_url == origin.rstrip("/")


@pytest.mark.parametrize("origin", [
    "",
    "admin.example",
    "http://admin.example",
    "https://user:secret@admin.example",
    "https://admin.example/path",
    "https://admin.example?token=secret",
    "https://admin.example#fragment",
    "https://admin.example?",
    "https://admin.example#",
    "https://admin.example\\path",
    "https://admin.example\n",
    "https://admin.example/\t",
    " https://admin.example",
    "https://",
    "https://admin.example:0",
    "https://admin.example:invalid",
])
def test_public_site_origin_rejects_unsafe_or_nonorigin_urls(origin: str) -> None:
    with pytest.raises(ValidationError):
        AppConfig(endpoints={"site_base_url": origin})
