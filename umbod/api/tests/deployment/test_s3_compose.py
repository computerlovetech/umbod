import pytest

from tests.deployment.test_proxy_compose import authentication_compose_configuration


@pytest.mark.parametrize("backend", ["local", "s3"])
def test_compose_workers_share_content_configuration_and_provider_credentials(backend: str) -> None:
    settings = {
        "UMBOD_FILESYSTEM_CONTENT_BACKEND": backend,
        "UMBOD_FILESYSTEM_UPLOAD_MAX_BYTES": "20971520",
        "UMBOD_FILESYSTEM_S3_BUCKET": "content-bucket" if backend == "s3" else "",
        "UMBOD_FILESYSTEM_S3_REGION": "eu-west-1" if backend == "s3" else "us-east-1",
        "UMBOD_FILESYSTEM_S3_ENDPOINT_URL": "https://storage.example.test" if backend == "s3" else "",
        "UMBOD_FILESYSTEM_S3_PREFIX": "tenant/content" if backend == "s3" else "",
        "UMBOD_FILESYSTEM_S3_ADDRESSING_STYLE": "path" if backend == "s3" else "auto",
        "AWS_ACCESS_KEY_ID": "compose-access-key",
        "AWS_SECRET_ACCESS_KEY": "compose-secret-key",
        "AWS_SESSION_TOKEN": "compose-session-token",
    }
    configuration = authentication_compose_configuration(settings)

    for service in ("api", "mcp"):
        environment = configuration["services"][service]["environment"]
        assert {name: environment[name] for name in settings} == settings


def test_compose_local_content_directory_remains_explicitly_configurable() -> None:
    settings = {"UMBOD_FILESYSTEM_CONTENT_DIRECTORY": "/app/data/custom-content"}
    configuration = authentication_compose_configuration(settings)

    for service in ("api", "mcp"):
        assert configuration["services"][service]["environment"]["UMBOD_FILESYSTEM_CONTENT_DIRECTORY"] == settings["UMBOD_FILESYSTEM_CONTENT_DIRECTORY"]
