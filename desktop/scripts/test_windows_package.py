"""Behavioral archive tests; fixtures are synthetic PE images, never runnable apps."""
import hashlib
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = pathlib.Path(__file__).with_name('package-windows.py')


def pe():
    data = bytearray(256)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 128)
    data[128:132] = b'PE\0\0'
    struct.pack_into('<H', data, 132, 0x8664)
    return data


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='umbod-package-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.publish = self.root / 'publish'
        self.publish.mkdir()
        (self.publish / 'Umbod.Windows.exe').write_bytes(pe())
        (self.publish / 'Umbod.Windows.dll').write_bytes(pe())
        (self.publish / 'Umbod.Windows.deps.json').write_text('{}')
        (self.publish / 'Umbod.Windows.runtimeconfig.json').write_text('{}')
        self.backend = self.root / 'umbod-gateway.exe'
        self.backend.write_bytes(pe())
        self.output = self.root / 'output'

    def invoke(self, channel='release'):
        return subprocess.run([sys.executable, str(SCRIPT), '--publish', str(self.publish),
            '--gateway', str(self.backend), '--channel', channel, '--output', str(self.output)],
            capture_output=True, text=True)

    def test_archive_has_ui_same_backend_profile_and_verified_checksum(self):
        for channel in ('release', 'dev'):
            with self.subTest(channel=channel):
                result = self.invoke(channel)
                self.assertEqual(result.returncode, 0, result.stderr)
                version = (SCRIPT.parent.parent / 'VERSION').read_text().strip()
                archive = self.output / f'Umbod-{version}-{channel}-win-x64.zip'
                with zipfile.ZipFile(archive) as package:
                    self.assertEqual(package.read('umbod-gateway.exe'), self.backend.read_bytes())
                    self.assertEqual(package.read('umbod-profile'), (channel + '\n').encode())
                    self.assertIn('Umbod.Windows.exe', package.namelist())
                    self.assertIn('README.txt', package.namelist())
                    manifest = json.loads(package.read('package-manifest.json'))
                    self.assertEqual(manifest['profile'], channel)
                    for name, digest in manifest['sha256'].items():
                        self.assertEqual(hashlib.sha256(package.read(name)).hexdigest(), digest)
                self.assertIn(hashlib.sha256(archive.read_bytes()).hexdigest(),
                              archive.with_suffix('.zip.sha256').read_text())

    def test_rejects_non_windows_backend_without_creating_archive(self):
        self.backend.write_bytes(b'#!/bin/sh\n')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Windows x64 PE', result.stderr)
        self.assertFalse(list(self.output.glob('*.zip')))

    def test_rejects_missing_ui_dependency_manifest(self):
        (self.publish / 'Umbod.Windows.deps.json').unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Umbod.Windows.deps.json', result.stderr)

    def test_refuses_migration_and_client_configuration_backups(self):
        for name in ('config.before-shared-permissions.json', '.umbod-fixture.backup'):
            with self.subTest(name=name):
                backup = self.publish / name
                backup.write_text('{"fixture":"private backup"}')
                try:
                    result = self.invoke()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name, result.stderr)
                finally:
                    backup.unlink()

    def test_refuses_runtime_secrets_and_symlinks(self):
        (self.publish / 'runtime.json').write_text('{"admin_token":"fixture-only"}')
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('runtime.json', result.stderr)
        (self.publish / 'runtime.json').unlink()
        try:
            (self.publish / 'linked.dll').symlink_to(self.backend)
        except OSError:
            return  # Windows without symlink privilege still tests secret rejection.
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('link', result.stderr.lower())


if __name__ == '__main__':
    unittest.main(verbosity=2)
