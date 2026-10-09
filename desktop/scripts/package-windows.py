#!/usr/bin/env python3
"""Package build outputs only; never reads installed Umbod data or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from release import version
import struct
import tempfile
import zipfile


def windows_x64(path):
    data = path.read_bytes()
    try:
        offset = struct.unpack_from('<I', data, 0x3c)[0]
        valid = (data[:2] == b'MZ' and data[offset:offset + 4] == b'PE\0\0'
                 and struct.unpack_from('<H', data, offset + 4)[0] == 0x8664)
    except struct.error:
        valid = False
    if not valid:
        raise ValueError(f'{path.name} must be a Windows x64 PE executable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', type=Path, required=True)
    parser.add_argument('--gateway', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--channel', choices=('dev', 'release'), default='dev')
    args = parser.parse_args()
    for name in ('Umbod.Windows.exe', 'Umbod.Windows.dll', 'Umbod.Windows.deps.json',
                 'Umbod.Windows.runtimeconfig.json'):
        if not (args.publish / name).is_file():
            raise ValueError(f'Missing required UI build output: {name}')
    windows_x64(args.publish / 'Umbod.Windows.exe')
    windows_x64(args.gateway)
    files = {}
    prohibited = {'runtime.json', 'config.json', 'owner.lock', 'umbod-profile',
                  'package-manifest.json', 'umbod-gateway.exe',
                  'config.before-shared-permissions.json'}
    if args.publish.is_symlink() or args.gateway.is_symlink():
        raise ValueError('Build inputs must not be symbolic links')
    for path in sorted(args.publish.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'Refusing symbolic link in publish output: {path.name}')
        if path.is_file():
            if path.name.lower() in prohibited or path.suffix.lower() in ('.bak', '.backup', '.log'):
                raise ValueError(f'Refusing private data or reserved file: {path.name}')
            files[path.relative_to(args.publish).as_posix()] = path.read_bytes()
    files['umbod-gateway.exe'] = args.gateway.read_bytes()
    files['umbod-profile'] = (args.channel + '\n').encode()
    files['README.txt'] = (
        'Umbod Desktop for Windows x64\n\n'
        'Extract the entire ZIP to a folder you own, then run Umbod.Windows.exe.\n'
        'This build is unsigned. Do not disable Windows security to run it.\n'
        f'Profile: {args.channel}. Release and development data and credentials are separate.\n'
        'Closing the UI leaves the gateway running; use Settings to stop or restart it.\n'
        'Credentials use Windows Credential Manager; no plaintext fallback exists.\n'
        'For local connectors select a trusted .exe. Batch .cmd/.bat wrappers are unsupported;\n'
        'select the underlying executable (for example node.exe) with explicit arguments.\n'
        'See desktop/README.md in computerlovetech/umbod for validation and limitations.\n'
    ).encode()
    release_version = version()
    files['package-manifest.json'] = (json.dumps({
        'version': release_version, 'profile': args.channel, 'runtime': 'win-x64',
        'sha256': {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    }, indent=2) + '\n').encode()
    args.output.mkdir(parents=True, exist_ok=True)
    archive = args.output / f'Umbod-{release_version}-{args.channel}-win-x64.zip'
    handle, temporary = tempfile.mkstemp(prefix='.umbod-package-', suffix='.zip', dir=args.output)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as package:
            for name, data in sorted(files.items()):
                package.writestr(name, data)
        os.replace(temporary, archive)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n')
    print(archive)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit(str(error))
