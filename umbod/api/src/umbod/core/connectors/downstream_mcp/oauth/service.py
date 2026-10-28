"""Client-independent sign-in workflow. Hosts supply storage and transport only."""

import asyncio
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from mcp.client.auth import AuthorizationCodeResult
from mcp.shared.auth import OAuthClientInformationFull
from umbod.core.connectors.downstream_mcp.adapters.fastmcp.oauth import SignInRequired
from .discovery import registration_mode
from .ports import (
    AuthorizationBeginOptions,
    AuthorizationSessionFactory,
    CallbackResult,
    OAuthConnection,
    OAuthDiscovery,
    OAuthHost,
)
from .provider import CLIENT_METADATA_URL, OAuthFailure


class OAuthService:
    def __init__(
        self,
        host: OAuthHost,
        sessions: AuthorizationSessionFactory,
        discovery: OAuthDiscovery,
    ) -> None:
        self.host = host
        self.sessions = sessions
        self.discovery = discovery
        self.callbacks: dict[str, asyncio.Future] = {}
        self.expected_states: dict[str, str] = {}
        self.tasks: dict[str, asyncio.Task] = {}
        self.results: dict[str, str] = host.statuses
        self.errors: dict[str, str] = {}
        self.previews: dict[str, dict] = {}
        self.stages: dict[str, str] = {}
        self.events: dict[str, list[dict]] = {}

    def _shared_connection(self, key: str) -> OAuthConnection:
        connection = self.host.connection(key)
        if connection.authorization_mode != "shared":
            raise ValueError("Personal OAuth cannot use shared authorization operations")
        return connection

    async def begin(self, key: str, client_id: str, scopes: str | None) -> dict:
        server = self._shared_connection(key)
        if urlsplit(server.endpoint_url).scheme != "https":
            raise ValueError("Browser sign-in requires an HTTPS connector")
        if key in self.tasks and not self.tasks[key].done():
            raise ValueError("Browser sign-in is already in progress")
        if scopes is not None:
            if not isinstance(scopes, str):
                raise ValueError("OAuth scopes must be a space-separated string")
            self.host.set_scopes(key, " ".join(scopes.split()))
            server = self._shared_connection(key)
        # Registration binds the client to this URI. State remains fresh per attempt;
        # the path must survive retries and application restarts.
        nonce = key
        redirect_uri = self.host.callback_url(key, shared=False)
        callback = asyncio.get_running_loop().create_future()
        redirect = asyncio.get_running_loop().create_future()
        storage = self.host.storage(key)
        await storage.load()
        registered = storage.document.client_info
        preview = self.previews.get(key, {})
        use_metadata = (
            not client_id
            and registered is None
            and preview.get("registration") == "hosted_metadata"
        ) or (
            registered is not None
            and registered.client_id == CLIENT_METADATA_URL
            and not client_id
        )
        if use_metadata:
            redirect_uri = self.host.callback_url(key, shared=True)
        if (
            registered
            and registered.redirect_uris
            and (
                (
                    not use_metadata
                    and redirect_uri
                    not in {str(uri) for uri in registered.redirect_uris}
                )
                or registered.token_endpoint_auth_method not in {None, "none"}
            )
        ):
            storage.document.client_info = None
            storage.document.tokens = None
            storage.document.expires_at = None
            await storage.save()
        if client_id:
            storage.document.client_info = OAuthClientInformationFull(
                client_id=client_id
            )
            storage.document.tokens = None
            storage.document.expires_at = None
            await storage.save()

        self.callbacks[nonce] = callback

        async def redirect_handler(url: str) -> None:
            self.record(key, "browser", False)
            self.expected_states[nonce] = parse_qs(urlsplit(url).query)["state"][0]
            if not redirect.done():
                redirect.set_result(url)

        async def callback_handler() -> AuthorizationCodeResult:
            async with asyncio.timeout(300):
                return await callback

        session = self.sessions.begin(
            storage,
            AuthorizationBeginOptions(
                endpoint=server.endpoint_url,
                requested_scopes=server.requested_scopes,
                metadata_mode="hosted_metadata" if use_metadata else "registration",
                redirect_uri=redirect_uri,
            ),
            redirect_handler,
            callback_handler,
        )

        async def authorize() -> None:
            try:
                async with session:
                    self.record(key, "discovery", False)
                    await session.discover_tools()
                self.host.set_authorized(key, True)
                await self.host.reconnect(key)
                self.results[key] = "signed_in"
                self.record(key, "connected", False)
                if not redirect.done():
                    redirect.set_result("")
            except Exception as exc:  # noqa: BLE001 - never expose upstream exception text
                authorized = session.token_received
                if authorized:
                    self.host.set_authorized(key, True)
                self.results[key] = "discovery_failed" if authorized else "failed"
                self.record(
                    key,
                    "discovery"
                    if authorized
                    else self.stages.get(key, "authorization"),
                    failed=True,
                )
                self.errors[key] = self.failure_message(exc)
                if not redirect.done():
                    redirect.set_exception(ValueError("Browser sign-in failed"))
            finally:
                if not redirect.done():
                    redirect.set_result("")
                self.callbacks.pop(nonce, None)
                self.expected_states.pop(nonce, None)

        self.record(key, "discovery", False)
        self.results[key] = "pending"
        self.errors.pop(key, None)
        self.tasks[key] = asyncio.create_task(authorize())
        try:
            async with asyncio.timeout(30):
                url = await asyncio.shield(redirect)
        except TimeoutError, asyncio.CancelledError:
            await self.cancel(key)
            raise
        return {"url": url, "status": self.results.get(key, "pending")}

    def record(self, key, stage, failed):
        self.stages[key] = stage
        events = self.events.setdefault(key, [])
        events.append(
            {
                "time": int(time.time()),
                "stage": stage,
                "result": "failed" if failed else "started",
            }
        )
        del events[:-20]

    async def discover(self, key: str) -> dict:
        server = self._shared_connection(key)
        self.record(key, "metadata", False)
        preview = await self.discovery.discover(server.endpoint_url)
        self.previews[key] = preview.model_dump(mode="json")
        return {**await self.details(key), **self.previews[key]}

    async def details(self, key: str) -> dict:
        server = self._shared_connection(key)
        storage = self.host.storage(key)
        await storage.load()
        document = storage.document
        metadata = document.metadata
        return {
            "status": self.results.get(key, "signed_out"),
            "error": self.errors.get(key),
            "callback_url": self.host.callback_url(
                key,
                shared=bool(
                    document.client_info
                    and document.client_info.client_id == CLIENT_METADATA_URL
                ),
            ),
            "has_authorization": document.tokens is not None,
            "has_refresh_token": bool(
                document.tokens and document.tokens.refresh_token
            ),
            "granted_scopes": document.tokens.scope if document.tokens else None,
            "requested_scopes": server.requested_scopes,
            "available_scopes": metadata.scopes_supported or [] if metadata else [],
            "registration": registration_mode(metadata),
            "stage": self.stages.get(key, "not_started"),
            "diagnostics": self.events.get(key, []),
            **self.previews.get(key, {}),
        }

    async def cancel(self, key: str) -> dict:
        self._shared_connection(key)
        task = self.tasks.get(key)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.results[key] = "cancelled"
        self.errors.pop(key, None)
        self.record(key, "cancelled", False)
        return {"status": "cancelled"}

    @staticmethod
    def failure_message(exc: BaseException) -> str:
        # Provider errors can contain tokens and callback URLs. Expose only known
        # categories, including errors wrapped by transport task groups.
        if isinstance(exc, OAuthFailure):
            return str(exc)
        if isinstance(exc, SignInRequired):
            return "The saved authorization could not be renewed. Sign in with browser again."
        if isinstance(exc, BaseExceptionGroup):
            return OAuthService.failure_message(exc.exceptions[0])
        if exc.__cause__ is not None:
            return OAuthService.failure_message(exc.__cause__)
        if type(exc).__name__ in {"MCPError", "McpError"}:
            return "The MCP server rejected connection or tool discovery. Authorization may already be saved. Check the server’s access settings, then retry discovery."
        if type(exc).__name__ == "OAuthFlowError" and str(exc).startswith(
            "Protected resource "
        ):
            return "The provider advertises a different MCP endpoint. Use its canonical endpoint URL in Edit connection, then sign in again."
        messages = {
            "OAuthTokenError": "The provider rejected the token exchange. Try signing in again.",
            "OAuthRegistrationError": "This provider requires a registered OAuth client. Enter its client ID in Connection settings.",
            "OAuthFlowError": "The provider's OAuth response could not be validated. Try signing in again.",
            "TimeoutError": "Browser sign-in timed out. Return to Connection settings and try again.",
            "ConnectError": "Could not reach the provider. Check your connection and try again.",
            "ReadTimeout": "The provider took too long to respond. Try signing in again.",
            "ValidationError": "The provider returned an unsupported sign-in or tool response.",
        }
        return messages.get(
            type(exc).__name__,
            "Sign-in or tool discovery failed. Try again in Connection settings.",
        )

    async def callback(self, nonce: str | None, parameters: dict[str, str]):
        state = parameters.get("state", "")
        if nonce is None:
            nonce = next(
                (
                    key
                    for key, expected in self.expected_states.items()
                    if secrets.compare_digest(state, expected)
                ),
                "",
            )
        future = self.callbacks.get(nonce)
        if future is None or future.done():
            return CallbackResult(
                "Sign-in has expired. Return to Umbod and retry.", status_code=400
            )
        if self.host.connection(nonce).authorization_mode != "shared":
            return CallbackResult("Personal authorization is not available here.", status_code=400)
        code, state = (
            parameters.get("code"),
            parameters.get("state"),
        )
        if not state or not secrets.compare_digest(
            state, self.expected_states.get(nonce, "")
        ):
            return CallbackResult("Missing authorization response.", status_code=400)
        if parameters.get("error"):
            future.set_exception(ValueError("Browser authorization was declined"))
            return CallbackResult(
                "Sign-in was not approved. Return to Umbod to try again."
            )
        if not code:
            return CallbackResult("Missing authorization response.", status_code=400)
        self.record(nonce, "token_exchange", False)
        future.set_result(
            AuthorizationCodeResult(code=code, state=state, iss=parameters.get("iss"))
        )
        return CallbackResult(
            "Authorization received. Return to Umbod to check the result."
        )

    async def refresh(self, key: str) -> dict:
        self._shared_connection(key)
        self.record(key, "refresh", False)
        try:
            result = await self._refresh(key)
        except Exception as exc:  # noqa: BLE001 - sanitize transport task groups too
            self.record(key, "refresh", failed=True)
            self.errors[key] = (
                "Could not refresh authorization. Use Sign in with browser to reconnect. "
                + self.failure_message(exc)
            )
            raise OAuthFailure(self.errors[key]) from None
        self.errors.pop(key, None)
        self.results[key] = "signed_in"
        self.record(key, "connected", False)
        return result

    async def _refresh(self, key: str) -> dict:
        self._shared_connection(key)
        storage = self.host.storage(key)
        await storage.load()
        if storage.document.tokens is None or not storage.document.tokens.refresh_token:
            raise OAuthFailure(
                "This provider did not issue a refresh token. Sign in with browser to renew access."
            )
        async with self.sessions.refresh(storage) as session:
            await session.discover_tools()
        await self.host.reconnect(key)
        return {"status": "refreshed"}

    async def forget(self, key: str) -> None:
        self._shared_connection(key)
        task = self.tasks.get(key)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await self.host.delete_authorization(key)
        self.results.pop(key, None)
        self.errors.pop(key, None)
        self.previews.pop(key, None)
        self.events.pop(key, None)
        self.stages.pop(key, None)
        self.tasks.pop(key, None)

    async def logout(self, key: str) -> None:
        await self.forget(key)
        self.host.set_authorized(key, False)
        self.results[key] = "sign_in_required"
        await self.host.reconnect(key)

    async def close(self):
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
