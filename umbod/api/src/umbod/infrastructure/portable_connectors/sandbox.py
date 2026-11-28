from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from pydantic import JsonValue
from pydantic_monty import (
    AsyncMonty,
    AsyncMontySession,
    ExternalModule,
    MontyError,
    MountDir,
    ResourceLimits,
)

from umbod.core.connectors.portable.ports import (
    HttpDispatch,
    PortableExecutionError,
    PortableSession,
)


_SDK_DIRECTORY = "/sdk"
PORTABLE_LIMITS: ResourceLimits = {
    "max_feed_duration_secs": 5,
    "max_memory": 32_000_000,
    "max_recursion_depth": 128,
    "max_total_sleep_secs": 5,
}
_INVOKE = "connector._handler(_umbod_handler_id)(**_umbod_arguments)"
_INVOKE_HTTP = (
    "from umbod_http_binding import dispatch as _umbod_dispatch\n"
    "from umbod_sdk.connectors.http import HttpContext as _UmbodHttpContext\n"
    "await connector._handler(_umbod_handler_id)(context=_UmbodHttpContext(dispatch=_umbod_dispatch), **_umbod_arguments)"
)


@contextmanager
def portable_sdk_mount() -> Iterator[MountDir]:
    sdk_sources = files("umbod_sdk.connectors")
    with TemporaryDirectory() as directory:
        root = Path(directory)
        package = root / "umbod_sdk"
        connectors = package / "connectors"
        connectors.mkdir(parents=True)
        (package / "__init__.py").touch()
        (connectors / "__init__.py").write_bytes(
            sdk_sources.joinpath("declaration.py").read_bytes()
        )
        (connectors / "http.py").write_bytes(
            sdk_sources.joinpath("http.py").read_bytes()
        )
        with MountDir(
            host_path=root, virtual_path=_SDK_DIRECTORY, mode="read-only"
        ) as mount:
            yield mount


def discard_output(_stream: Literal["stdout", "stderr"], _text: str) -> None:
    return


async def bootstrap_portable_sdk(session: AsyncMontySession, sdk_mount: MountDir) -> None:
    await session.feed_run(
        "import umbod_sdk.connectors.http",
        mount=sdk_mount,
        cwd=_SDK_DIRECTORY,
        print_callback=discard_output,
    )


class MontyPortableSandbox:
    def __init__(self, pool: AsyncMonty, sdk_mount: MountDir) -> None:
        self._pool = pool
        self._sdk_mount = sdk_mount

    @asynccontextmanager
    async def open(
        self, source: str, dispatch: HttpDispatch
    ) -> AsyncIterator[PortableSession]:
        modules = {"umbod_http_binding": ExternalModule({"dispatch": dispatch})}
        try:
            async with self._pool.checkout(limits=PORTABLE_LIMITS, external_modules=modules) as session:
                await bootstrap_portable_sdk(session, self._sdk_mount)
                await session.feed_run(source, cwd="/", print_callback=discard_output)
                yield _MontyPortableSession(session)
        except MontyError:
            raise PortableExecutionError("Could not load or release portable connector session") from None


class _MontyPortableSession:
    def __init__(self, session: AsyncMontySession) -> None:
        self._session = session

    async def manifest(self) -> object:
        return await self._feed("connector.manifest()", inputs={})

    async def run(
        self, handler_id: str, arguments: dict[str, JsonValue], *, use_http: bool
    ) -> object:
        return await self._feed(
            _INVOKE_HTTP if use_http else _INVOKE,
            inputs={"_umbod_handler_id": handler_id, "_umbod_arguments": arguments},
        )

    async def _feed(self, code: str, *, inputs: dict[str, object]) -> object:
        try:
            return await self._session.feed_run(
                code, inputs=inputs, print_callback=discard_output
            )
        except MontyError:
            raise PortableExecutionError(
                "Portable connector execution failed."
            ) from None
