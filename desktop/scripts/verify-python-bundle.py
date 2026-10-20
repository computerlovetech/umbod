#!/usr/bin/env python3
"""Run with the bundled Python (-I -B) to reject checkout-dependent builds."""
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys


def require_bundled(path, prefix):
    if not Path(path).resolve().is_relative_to(prefix.resolve()):
        raise ValueError(f"Python bundle references an external path: {path}")


def verify_installation(prefix, paths, distributions):
    for path in paths:
        require_bundled(path, prefix)
    for distribution in distributions:
        direct_url = distribution.read_text("direct_url.json")
        if direct_url and json.loads(direct_url).get("dir_info", {}).get("editable"):
            raise ValueError(f"Editable distribution in Python bundle: {distribution.metadata['Name']}")
    # Nonexistent checkout paths are silently omitted from sys.path by site.py.
    # Inspect them too, so a broken release fails even on a clean build machine.
    for pth in prefix.glob("lib/python*/site-packages/*.pth"):
        for line in pth.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "import ", "import\t")):
                require_bundled(pth.parent / line, prefix)


def main() -> None:
    prefix = Path(sys.prefix)
    verify_installation(prefix, sys.path, importlib.metadata.distributions())
    # Exercise the real CLI import graph as well as REST/MCP entry points.
    for name in (
        "umbod_desktop.main",
        "umbod_desktop.runtime",
        "umbod.hosting",
        "umbod.core",
        "umbod.rest.main",
        "umbod.mcp.public_app",
        "umbod_sdk",
    ):
        module = importlib.import_module(name)
        if module.__file__:
            require_bundled(module.__file__, prefix)
        for path in getattr(module, "__path__", ()):
            require_bundled(path, prefix)
    print("PASS: bundled Python imports without editable or external source paths")


if __name__ == "__main__":
    main()
