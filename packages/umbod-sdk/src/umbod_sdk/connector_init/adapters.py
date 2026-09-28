import os
import stat
from contextlib import ExitStack
from pathlib import Path

from umbod_sdk.connector_init.models import InitRequest, ProjectSnapshot
from umbod_sdk.connector_init.port import InitError


class InMemoryProjectFiles:
    def __init__(self, metadata: bytes, package: str, project_directory: str = ".") -> None:
        self.metadata = metadata
        self.package = package
        self.project_directory = project_directory
        self.modules: dict[str, bytes] = {}
        self.package_directories: set[str] = set()

    def inspect(self, request: InitRequest) -> ProjectSnapshot:
        if request.project_directory != self.project_directory or request.module.split(".")[0] != self.package:
            raise InitError("Project or src package does not exist")
        if request.module in self.modules or request.module in self.package_directories:
            raise InitError("Connector module or package already exists")
        return ProjectSnapshot(metadata=self.metadata)

    def create_module(self, request: InitRequest, source: bytes) -> None:
        self.inspect(request)
        self.modules[request.module] = source

    def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None:
        if self.metadata != expected:
            raise InitError("pyproject.toml changed since preview")
        self.metadata += addition


class FilesystemProjectFiles:
    def _directory(self, path: Path, stack: ExitStack) -> int:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        stack.callback(os.close, descriptor)
        for component in path.parts[1:]:
            descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            stack.callback(os.close, descriptor)
        return descriptor

    def _directories(self, request: InitRequest, stack: ExitStack) -> tuple[int, int]:
        root = Path(os.path.abspath(request.project_directory))
        project = self._directory(root, stack)
        package = request.module.split(".")[0]
        src = os.open("src", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=project)
        stack.callback(os.close, src)
        package_dir = os.open(package, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=src)
        stack.callback(os.close, package_dir)
        return project, package_dir

    def _regular_file(self, name: str, directory: int, flags: int, stack: ExitStack) -> int:
        descriptor = os.open(name, flags | os.O_NOFOLLOW, dir_fd=directory)
        stack.callback(os.close, descriptor)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise InitError(f"{name} must be a regular file")
        return descriptor

    def _check_target(self, request: InitRequest, package_dir: int) -> str:
        module = request.module.split(".")[1]
        for name in (f"{module}.py", module):
            try:
                target = os.stat(name, dir_fd=package_dir, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(target.st_mode):
                raise InitError("Connector target is symlinked")
            raise InitError("Connector module or package already exists")
        return f"{module}.py"

    def inspect(self, request: InitRequest) -> ProjectSnapshot:
        try:
            with ExitStack() as stack:
                project, package_dir = self._directories(request, stack)
                metadata = self._regular_file("pyproject.toml", project, os.O_RDONLY, stack)
                self._regular_file("__init__.py", package_dir, os.O_RDONLY, stack)
                self._check_target(request, package_dir)
                with os.fdopen(os.dup(metadata), "rb") as input_file:
                    return ProjectSnapshot(metadata=input_file.read())
        except OSError as error:
            raise InitError(f"Cannot inspect project paths (symlinked paths are not supported): {error}") from error

    def create_module(self, request: InitRequest, source: bytes) -> None:
        module = request.module.split(".")[1] + ".py"
        try:
            with ExitStack() as stack:
                project, package_dir = self._directories(request, stack)
                self._regular_file("pyproject.toml", project, os.O_RDONLY, stack)
                self._regular_file("__init__.py", package_dir, os.O_RDONLY, stack)
                self._check_target(request, package_dir)
                descriptor = os.open(module, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666, dir_fd=package_dir)
                stack.callback(os.close, descriptor)
                with os.fdopen(os.dup(descriptor), "wb") as output:
                    output.write(source)
        except OSError as error:
            raise InitError(f"Cannot create module {module}: {error}; inspect project for a partial module") from error

    def _append(self, descriptor: int, addition: bytes) -> None:
        written = os.write(descriptor, addition)
        if written != len(addition):
            raise InitError("Incomplete metadata append")

    def append_metadata(self, request: InitRequest, expected: bytes, addition: bytes) -> None:
        try:
            with ExitStack() as stack:
                project, package_dir = self._directories(request, stack)
                self._regular_file("__init__.py", package_dir, os.O_RDONLY, stack)
                self._regular_file(request.module.split(".")[1] + ".py", package_dir, os.O_RDONLY, stack)
                descriptor = self._regular_file("pyproject.toml", project, os.O_RDWR | os.O_APPEND, stack)
                with os.fdopen(os.dup(descriptor), "rb") as input_file:
                    if input_file.read() != expected:
                        raise InitError("pyproject.toml changed since preview")
                self._append(descriptor, addition)
                os.lseek(descriptor, 0, os.SEEK_SET)
                with os.fdopen(os.dup(descriptor), "rb") as input_file:
                    if input_file.read() != expected + addition:
                        raise InitError("pyproject.toml changed during append; inspect partial state")
        except OSError as error:
            raise InitError(f"Cannot append pyproject.toml: {error}; inspect partial state") from error
