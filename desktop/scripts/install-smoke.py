#!/usr/bin/env python3
"""Install the actual DMG into a disposable directory and verify its bundled runtime."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    desktop = Path(__file__).resolve().parents[1]
    archive = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix="umbod-test-install-") as temporary:
        root = Path(temporary)
        mount = root / "volume"
        app = root / "Applications" / "Umbod.app"
        subprocess.run(["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", str(mount), str(archive)], check=True)
        try:
            app.parent.mkdir()
            subprocess.run(["ditto", str(mount / "Umbod.app"), str(app)], check=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        subprocess.run([str(app / "Contents/Resources/python/bin/python3"), "-I", "-B", str(desktop / "scripts/verify-python-bundle.py")], check=True)
        environment = {**os.environ, "UMBOD_TEST_APP": str(app)}
        # Swift drives the tests; every backend and agent process uses the installed interpreter.
        subprocess.run(["/usr/bin/xcrun", "--toolchain", "XcodeDefault", "--sdk", "macosx", "swift", "run", "--package-path", str(desktop / "native"), "UmbodTests"], env=environment, check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(app)], check=True)
        print("PASS: DMG install, packaged agent flow, and persistence")


if __name__ == "__main__":
    main()
