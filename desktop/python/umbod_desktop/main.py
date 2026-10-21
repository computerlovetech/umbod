"""Packaged host entrypoint and stdio bridge; stdout is protocol-only."""

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
import socket
import sys
from pathlib import Path

import uvicorn

from .backward_compatibility.adapters.legacy_host import retire_legacy_host
from .backward_compatibility.profile import saved_legacy_port
from .endpoint import saved_port
from .models import loopback_origin
from .security import KeychainVault, persistent_secret
from .storage import atomic_json


def default_directory(profile: str) -> Path:
    return (
        Path.home()
        / "Library/Application Support"
        / ("Umbod Dev" if profile == "dev" else "Umbod")
    )


def credential_namespace(directory: Path, profile: str) -> str:
    if directory.resolve() == default_directory(profile).resolve():
        return ""
    return ".test." + hashlib.sha256(str(directory.resolve()).encode()).hexdigest()[:20]


def credential_vault(arguments, directory):
    if arguments.test_credentials:
        if arguments.data_dir is None:
            raise ValueError("Test credentials require explicit temporary data")
        from .testing import FixtureVault

        return FixtureVault(directory)
    if (
        directory.name.startswith("umbod-test-")
        or (directory / "fixture-credentials.json").exists()
    ):
        raise ValueError("Fixture directories must explicitly select test credentials")
    return KeychainVault(
        arguments.profile, credential_namespace(directory, arguments.profile)
    )


def bundled_profile() -> str:
    marker = Path(sys.executable).parent.parent.parent / "umbod-profile"
    profile = marker.read_text().strip() if marker.exists() else "dev"
    if profile not in ("dev", "release"):
        raise ValueError("Invalid bundled profile")
    return profile


def owns_profile(
    directory: Path, identity: tuple[int, int], lock_identity: tuple[int, int]
) -> bool:
    """A moved/replaced profile must not leave a host reading its replacement."""
    try:
        current = directory.stat()
        lock = (directory / "python.lock").stat()
        return (current.st_dev, current.st_ino) == identity and (
            lock.st_dev,
            lock.st_ino,
        ) == lock_identity
    except OSError:
        return False


async def watch_profile(directory, identity, lock_identity, shutdown):
    while owns_profile(directory, identity, lock_identity):
        await asyncio.sleep(0.5)
    shutdown()


async def serve(arguments) -> None:
    from .runtime import create_desktop_app

    startup_output = sys.stdout
    sys.stdout = sys.stderr
    directory = arguments.data_dir or default_directory(arguments.profile)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink() or directory.stat().st_uid != os.getuid():
        raise ValueError("Desktop data must be an owned directory")
    os.chmod(directory, 0o700)
    os.umask(0o077)
    with (directory / "python.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory_stat, lock_stat = directory.stat(), os.fstat(lock.fileno())
        identity = (directory_stat.st_dev, directory_stat.st_ino)
        lock_identity = (lock_stat.st_dev, lock_stat.st_ino)
        await retire_legacy_host(directory, arguments.profile)
        endpoint_path = directory / "python-endpoint.json"
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", saved_port(directory, saved_legacy_port)))
            listener.listen(128)
            port = listener.getsockname()[1]
            origin = f"http://127.0.0.1:{port}"
            vault = credential_vault(arguments, directory)
            server = None

            def shutdown():
                server.should_exit = True

            app, token = await create_desktop_app(
                directory, arguments.profile, origin, vault, shutdown
            )
            server = uvicorn.Server(
                uvicorn.Config(
                    app, log_config=None, access_log=False, timeout_graceful_shutdown=10
                )
            )
            task = asyncio.create_task(server.serve(sockets=[listener]))
            ownership_task = asyncio.create_task(
                watch_profile(directory, identity, lock_identity, shutdown)
            )
            try:
                while not server.started:
                    if task.done():
                        await task
                        raise RuntimeError("Python backend failed to start")
                    await asyncio.sleep(0.02)
                record = {
                    "profile": arguments.profile,
                    "pid": os.getpid(),
                    "management": f"127.0.0.1:{port}",
                    "gateway": f"127.0.0.1:{port}",
                    "backend": "python",
                    "protocol": 2,
                }
                atomic_json(endpoint_path, {"port": port})
                atomic_json(directory / "python-runtime.json", record)
                print(
                    json.dumps({**record, "admin_token": token}),
                    file=startup_output,
                    flush=True,
                )
                if not arguments.persistent:

                    async def watch_owner():
                        await asyncio.to_thread(sys.stdin.buffer.read)
                        server.should_exit = True

                    asyncio.create_task(watch_owner())
                await task
            finally:
                server.should_exit = True
                await task
                ownership_task.cancel()
                await asyncio.gather(ownership_task, return_exceptions=True)
                # Never remove a replacement host's record after a profile move.
                if owns_profile(directory, identity, lock_identity):
                    record_path = directory / "python-runtime.json"
                    try:
                        record = json.loads(record_path.read_text())
                        if record.get("pid") == os.getpid():
                            record_path.unlink(missing_ok=True)
                    except OSError, ValueError:
                        pass


async def bridge(arguments) -> None:
    from fastmcp.client.transports import StreamableHttpTransport
    from fastmcp.server import create_proxy

    directory = arguments.data_dir or default_directory(arguments.profile)
    record = json.loads((directory / "python-runtime.json").read_text())
    if record.get("profile") != arguments.profile or not record.get(
        "gateway", ""
    ).startswith("127.0.0.1:"):
        raise ValueError("Invalid desktop runtime identity")
    vault = credential_vault(arguments, directory)
    token = persistent_secret(vault, "python:agent-token")
    proxy = create_proxy(
        StreamableHttpTransport(
            loopback_origin(record["gateway"]) + "/mcp",
            headers={"Authorization": f"Bearer {token}"},
        )
    )
    await proxy.run_async(transport="stdio", show_banner=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "bridge", "credential"])
    parser.add_argument("legacy_client", nargs="?")
    parser.add_argument(
        "--profile", choices=["dev", "release"], default=bundled_profile()
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument(
        "--test-credentials", action="store_true", help=argparse.SUPPRESS
    )
    arguments = parser.parse_args()
    if arguments.command != "bridge" and arguments.legacy_client:
        parser.error("Only bridge accepts a legacy client identity")
    protocol_output = sys.stdout
    try:
        if arguments.command == "credential":
            directory = arguments.data_dir or default_directory(arguments.profile)
            value = credential_vault(arguments, directory).get("python:admin-token")
            if value is None:
                raise ValueError("Backend credential is missing")
            print(json.dumps({"admin_token": value}), flush=True)
            return
        asyncio.run(
            serve(arguments) if arguments.command == "serve" else bridge(arguments)
        )
    except Exception:  # noqa: BLE001 - boundary redacts upstream and vault secrets
        # Avoid reflecting connector credentials or upstream errors in protocol output.
        print(
            json.dumps(
                {
                    "error": "Python backend could not start. Check Keychain access, data directory, and the local port."
                }
            ),
            flush=True,
            file=sys.stderr if arguments.command == "bridge" else protocol_output,
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
