import base64
import ssl

import httpcore
import pytest
from pydantic import SecretStr

from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.network import SafeOAuthHttpTransport
from umbod.core.network import PublicAddressNetworkBackend
from umbod.core.connectors.downstream_mcp.adapters.personal_oauth.transport import BasicOAuthHttpAuthentication, OAuthHttpRequest, OAuthHttpTransport

from .test_network import MemoryNetwork, MemoryStream


@pytest.mark.asyncio
async def test_basic_credentials_are_individually_form_encoded_before_base64(public_dns: list[str]) -> None:
    stream = MemoryStream(content=b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
    network = MemoryNetwork(stream)
    command = OAuthHttpRequest(
        method="POST", url="https://issuer.example/token", content_type="application/x-www-form-urlencoded",
        body=SecretStr("grant_type=authorization_code&code=code"),
        authentication=BasicOAuthHttpAuthentication(client_id=SecretStr("client:+% ä"), client_secret=SecretStr("private:+% ö")),
    )
    async with httpcore.AsyncConnectionPool(
        network_backend=PublicAddressNetworkBackend(network), ssl_context=ssl.create_default_context(), retries=0,
    ) as pool:
        port: OAuthHttpTransport = SafeOAuthHttpTransport(pool)
        assert (await port.request(command)).status == 200
    expected = b"Basic " + base64.b64encode(b"client%3A%2B%25+%C3%A4:private%3A%2B%25+%C3%B6")
    authorization = [line.split(b":", 1)[1].strip() for line in bytes(stream.written).split(b"\r\n") if line.lower().startswith(b"authorization:")]
    assert authorization == [expected]
    assert "private:+% ö".encode() not in stream.written
    assert b"client_secret" not in stream.written
    assert public_dns == ["issuer.example"]
    assert "private:+% ö" not in repr(command)
