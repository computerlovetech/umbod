from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from umbod.core.connectors.downstream_mcp.personal_connections.oauth_callback_models import MissingCallbackIssuer, issuer_route_key
from umbod.rest.connectors.downstream_mcp.personal_connections.oauth_callback import CALLBACK_PATH

from test_personal_oauth_routes import OAuthApi, oauth_api as oauth_api


def test_issuer_callback_uses_mounted_deployment_root_without_authority_headers(oauth_api: OAuthApi) -> None:
    oauth_api.provider.bound_callback = True
    oauth_api.start()
    application = FastAPI()
    application.mount("/embedded", oauth_api.app)
    path = "/embedded" + CALLBACK_PATH + "/issuer/" + issuer_route_key("https://issuer.example")
    query = urlencode({"state": oauth_api.provider.preparations[-1].state.get_secret_value(), "code": "secret-code"})
    with TestClient(application) as client:
        response = client.get(path + "?" + query, headers={"Host": "untrusted.example", "X-Forwarded-Host": "wrong.example"})
    assert response.status_code == 200
    assert len(oauth_api.provider.exchanges) == 1
    assert isinstance(oauth_api.provider.exchanges[0].issuer, MissingCallbackIssuer)


@pytest.mark.parametrize("attack", ("generic", "wrong_hash", "mismatch", "empty", "error_mismatch", "percent_alias", "uppercase", "extra_segment", "extra_slash"))
def test_bound_callback_rejects_wrong_route_or_issuer_without_consuming_attempt(oauth_api: OAuthApi, attack: str) -> None:
    oauth_api.provider.bound_callback = True
    attempt = oauth_api.start()
    issuer_key = issuer_route_key("https://issuer.example")
    path = CALLBACK_PATH + "/issuer/" + issuer_key
    parameters = {"state": oauth_api.provider.preparations[-1].state.get_secret_value(), "code": "secret-code"}
    if attack == "generic":
        path = CALLBACK_PATH
        parameters["iss"] = "https://issuer.example"
    elif attack == "wrong_hash":
        path = CALLBACK_PATH + "/issuer/" + "0" * 64
    elif attack in ("mismatch", "empty", "error_mismatch"):
        parameters["iss"] = "" if attack == "empty" else "https://wrong.example"
        if attack == "error_mismatch":
            parameters.pop("code")
            parameters["error"] = "denied"
    elif attack == "percent_alias":
        path = path.replace("/issuer/", "/%69ssuer/")
    elif attack == "uppercase":
        path = CALLBACK_PATH + "/issuer/" + issuer_key.upper()
    elif attack == "extra_segment":
        path += "/extra"
    elif attack == "extra_slash":
        path += "/"
    rejected = oauth_api.client.get(path + "?" + urlencode(parameters), follow_redirects=False)
    assert rejected.status_code == 400
    assert "Return to Connections" in rejected.text
    assert "Cancel it or wait for expiry" in rejected.text
    assert "secret-code" not in rejected.text
    assert not oauth_api.provider.exchanges
    status_url = oauth_api.url + "/" + attempt["attempt_id"]
    assert oauth_api.client.get(status_url, headers={"X-Access": "alice"}).json()["status"] == "pending"
    accepted = oauth_api.client.get(CALLBACK_PATH + "/issuer/" + issuer_key + "?" + urlencode({
        "state": parameters["state"], "code": "secret-code",
    }))
    assert accepted.status_code == 200
    assert isinstance(oauth_api.provider.exchanges[0].issuer, MissingCallbackIssuer)
    assert oauth_api.provider.exchanges[0].route.issuer_key == issuer_key
    assert oauth_api.client.get(status_url, headers={"X-Access": "alice"}).json()["status"] == "completed"
    assert oauth_api.client.get(accepted.request.url).status_code == 400
