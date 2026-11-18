import ast
import inspect

import umbod.mcp.filesystem as filesystem
import umbod.mcp.public_app as public_app


def test_public_interface_exposes_server_registration_dependencies() -> None:
    expected_exports = {
        "CurrentFilesystemCallerCapture",
        "DatabaseFilesystemServiceFactory",
        "FilesystemCallerCapture",
        "FilesystemDiscoveryRuntime",
        "FilesystemServiceFactory",
        "FilesystemToolVisibility",
        "FilesystemVisibilityMiddleware",
        "McpFilesystemDeletionApproval",
        "RuntimeFilesystemGroupClaimFields",
        "StaticFilesystemGroupClaimFields",
        "register_filesystem_resources",
        "register_filesystem_tools",
    }
    assert set(filesystem.__all__) == expected_exports
    for name in expected_exports:
        assert callable(getattr(filesystem, name))


def test_public_app_imports_only_the_supported_filesystem_interface() -> None:
    imports = ast.walk(ast.parse(inspect.getsource(public_app)))
    filesystem_imports: list[str] = []
    for node in imports:
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == "umbod.mcp.filesystem":
                filesystem_imports.extend(alias.name for alias in node.names)
            assert not node.module.startswith("umbod.mcp.filesystem.")
        elif isinstance(node, ast.Import):
            assert not any(alias.name.startswith("umbod.mcp.filesystem.") for alias in node.names)
    assert filesystem_imports
    assert set(filesystem_imports) <= set(filesystem.__all__)
    for name in filesystem_imports:
        assert getattr(public_app, name) is getattr(filesystem, name)
