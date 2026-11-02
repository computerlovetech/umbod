import re
from uuid import uuid4

import pytest

from tests.deployment.test_proxy_compose import authentication_compose_configuration


@pytest.fixture
def upload_transfer_labels() -> dict[str, str]:
    configuration = authentication_compose_configuration()
    return configuration["services"]["api"]["labels"]


def test_upload_transfer_router_uses_capability_authentication_without_browser_login(
    upload_transfer_labels: dict[str, str],
) -> None:
    labels = upload_transfer_labels
    prefix = "traefik.http.routers.umbod-upload-transfer"
    rule = labels[prefix + ".rule"]
    assert "Host(`umbod-admin.computerlove.tech`)" in rule
    assert "Method(`PUT`)" in rule
    assert labels[prefix + ".middlewares"] == "umbod-browser-response@docker"
    assert labels[prefix + ".service"] == "umbod-browser-api"
    assert int(labels[prefix + ".priority"]) > int(labels["traefik.http.routers.umbod-browser-api.priority"])


@pytest.mark.parametrize("suffix,allowed", [
    ("/transfer", True),
    ("/transfer/", False),
    ("/transfer/extra", False),
    ("/content", False),
    ("/complete", False),
    ("", False),
])
def test_upload_transfer_router_exempts_only_the_exact_transfer_path(
    upload_transfer_labels: dict[str, str], suffix: str, allowed: bool,
) -> None:
    rule = upload_transfer_labels["traefik.http.routers.umbod-upload-transfer.rule"]
    expression = rule.split("PathRegexp(`", 1)[1].split("`)", 1)[0]
    path = "/api/filesystem/uploads/" + str(uuid4()) + suffix
    assert bool(re.search(expression, path)) is allowed
    assert re.search(expression, "/api/filesystem/uploads/not-a-uuid/transfer") is None
