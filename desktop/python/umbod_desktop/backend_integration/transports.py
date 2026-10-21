import asyncio
import sys
from typing import Any
from uuid import uuid4

import httpx2
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fastmcp.server import create_proxy
from starlette.responses import JSONResponse
from starlette.types import Receive, Scope, Send

from ..contracts import (
    ConnectorBinding,
    PreparedUpstream,
    ProxyConfiguration,
    UpstreamInput,
)
from ..ports import CredentialVault
from ..security import LoopbackAuthentication
from ..storage import DesktopState
from .models import DesktopServer


class ProxyLifetime:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.ready = asyncio.get_running_loop().create_future()
        self.stopped = asyncio.Event()
        self.task = asyncio.create_task(self.run())

    async def run(self) -> None:
        try:
            async with self.app.lifespan(self.app):
                self.ready.set_result(None)
                await self.stopped.wait()
        except BaseException as error:
            if not self.ready.done():
                self.ready.set_exception(error)
            raise

    async def start(self) -> None:
        try:
            await self.ready
        except BaseException:
            await asyncio.gather(self.task, return_exceptions=True)
            raise

    async def aclose(self) -> None:
        self.stopped.set()
        await self.task


class DesktopUpstreams:
    def __init__(
        self, state: DesktopState, vault: CredentialVault, token: str, origin: str
    ) -> None:
        self.state, self.vault, self.token, self.origin = state, vault, token, origin
        self.apps: dict[str, object] = {}
        self.lifetimes: dict[str, ProxyLifetime] = {}
        self.authentication_status = {
            key: value
            for key, value in state.data.get("authentication_status", {}).items()
            if value in ("sign_in_required", "signed_out")
        }
        state.data["authentication_status"] = self.authentication_status

    def set_authentication_status(self, key: str, status: str) -> None:
        self.authentication_status[key] = status
        self.state.save()

    async def start(self, key: str, server: dict) -> None:
        headers = {
            name: self._credential(ref)
            for name, ref in server.get("headers", {}).items()
        }
        if server["transport"] == "stdio":
            env = {
                name: self._credential(ref)
                for name, ref in server.get("env", {}).items()
            }
            transport = StdioTransport(
                command=server["command"],
                args=server.get("args", []),
                env=env,
                log_file=sys.stderr,
            )
        elif server["transport"] == "http":
            auth = None
            if server.get("oauth"):
                from umbod.core.connectors.downstream_mcp.oauth.provider import (
                    RuntimeOAuth,
                )

                from .oauth import KeychainOAuthStorage

                auth = RuntimeOAuth(
                    KeychainOAuthStorage(self.vault, key, server["url"]),
                    lambda: self.set_authentication_status(key, "sign_in_required")
                )

            async def observe_response(response: httpx2.Response) -> None:
                if str(response.request.url).rstrip("/") != server["url"].rstrip("/"):
                    return
                from umbod.core.connectors.downstream_mcp.oauth.provider import (
                    response_authentication_status,
                )
                status = response_authentication_status(response.status_code, bool(server.get("oauth")))
                if status and self.authentication_status.get(key) != status:
                    self.authentication_status[key] = status
                    self.state.save()

            def http_client(**kwargs: Any) -> httpx2.AsyncClient:
                kwargs.setdefault("timeout", httpx2.Timeout(30.0, read=300.0))
                return httpx2.AsyncClient(
                    **kwargs, event_hooks={"response": [observe_response]}
                )

            transport = StreamableHttpTransport(
                server["url"],
                headers=headers,
                auth=auth,
                httpx_client_factory=http_client,
            )
        else:
            raise ValueError("Unsupported connector transport")
        proxy = create_proxy(
            transport,
            mode="auto",
            provider_error_strategy="raise",
            name=f"desktop-upstream-{key}",
        )
        app = proxy.http_app(path="/mcp")
        lifetime = ProxyLifetime(app)
        await lifetime.start()
        old = self.lifetimes.pop(key, None)
        self.apps[key] = LoopbackAuthentication(app, self.token, forward_authorization=False)
        self.lifetimes[key] = lifetime
        if old:
            await old.aclose()

    def _credential(self, reference: str) -> str:
        if not reference.startswith("upstream:"):
            raise ValueError("Only upstream credential references are allowed")
        value = self.vault.get(reference)
        if value is None:
            raise ValueError("A connector credential is missing from Keychain")
        return value

    async def prepare(self, server: UpstreamInput) -> PreparedUpstream:
        draft = DesktopServer.model_validate(server.root)
        server = draft.model_dump()
        key = server.get("host_id") or uuid4().hex
        if key not in self.state.data["servers"] and server.get("host_id"):
            raise ValueError("Unknown desktop connector")
        previous = self.state.data["servers"].get(key)
        connection_fields = (
            "transport",
            "command",
            "args",
            "url",
            "oauth",
            "headers",
            "env",
        )
        connection_changed = (
            draft.reconnect
            or previous is None
            or any(
                previous.get(field) != server.get(field) for field in connection_fields
            )
        )
        try:
            if connection_changed:
                await self.start(key, server)
                self.state.data.setdefault("transport_errors", {}).pop(key, None)
        except ValueError, OSError:
            old = self.lifetimes.pop(key, None)
            self.apps.pop(key, None)
            if old:
                await old.aclose()
            self.state.data.setdefault("transport_errors", {})[key] = (
                "Restore the executable or Keychain credential, then reconnect."
            )
        self.state.data["servers"][key] = {**server, "host_id": key}
        self.state.save()
        return PreparedUpstream(
            host_id=key,
            connection_changed=connection_changed,
            configuration=self.proxy_configuration(key),
        )

    def proxy_configuration(self, host_id: str) -> ProxyConfiguration:
        return ProxyConfiguration(
            auth_mode="static_bearer",
            endpoint_url=f"{self.origin}/desktop/upstreams/{host_id}/mcp",
            header_type="bearer",
            bearer_token=self.token,
        )

    def bind(self, binding: ConnectorBinding) -> None:
        self.state.data["servers"][binding.host_id]["id"] = binding.connector_id
        self.state.save()

    async def restore(self) -> None:
        errors = self.state.data.setdefault("transport_errors", {})
        for key, server in self.state.data["servers"].items():
            try:
                await self.start(key, server)
                errors.pop(key, None)
            except ValueError, OSError:
                errors[key] = (
                    "Reconnect this connector after restoring its executable or Keychain credentials."
                )
        self.state.save()

    async def close(self) -> None:
        for lifetime in self.lifetimes.values():
            await lifetime.aclose()
        self.lifetimes.clear()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        parts = scope["path"].split("/")
        key = parts[3] if len(parts) > 3 else ""
        app = self.apps.get(key)
        if app is None:
            await JSONResponse({"detail": "Not found"}, status_code=404)(
                scope, receive, send
            )
            return
        path = "/" + "/".join(parts[4:])
        await app(
            {**scope, "path": path, "raw_path": path.encode(), "root_path": ""},
            receive,
            send,
        )
