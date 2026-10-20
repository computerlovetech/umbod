#!/usr/bin/env python3
"""Record build inputs and remove Swift's development-only toolchain search path."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
app = Path(sys.argv[1])
resources = app / 'Contents/Resources'

def output(*args: str) -> str:
    return subprocess.check_output(args, text=True, cwd=root).strip()

metadata = {
    'schemaVersion': 1,
    'version': (root / 'desktop/VERSION').read_text().strip(),
    'sourceCommit': output('git', 'rev-parse', 'HEAD'),
    'dirty': bool(output('git', 'status', '--porcelain', '--untracked-files=no')),
    'architecture': output('uname', '-m'),
    'deploymentTarget': '14.0',
    'python': output(str(resources / 'python/bin/python3'), '-I', '-B', '--version'),
    'pythonBuild': (resources / 'python/BUILD').read_text().strip(),
    'uv': output('uv', '--version'),
    'swift': output('/usr/bin/xcrun', '--toolchain', 'XcodeDefault', '--sdk', 'macosx', 'swift', '--version'),
    'xcode': output('/usr/bin/xcodebuild', '-version'),
    'lockSha256': hashlib.sha256((root / 'desktop/python/uv.lock').read_bytes()).hexdigest(),
}
(resources / 'build-metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
binary = app / 'Contents/MacOS/Umbod'
lines = output('/usr/bin/otool', '-l', str(binary)).splitlines()
for i, line in enumerate(lines):
    if line.strip() == 'cmd LC_RPATH':
        path = lines[i + 2].strip().removeprefix('path ').split(' (offset')[0]
        if path.startswith('/') and '.xctoolchain/' in path:
            subprocess.run(['/usr/bin/install_name_tool', '-delete_rpath', path, str(binary)], check=True)
