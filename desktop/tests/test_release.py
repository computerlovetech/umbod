import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import runpy

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('release', ROOT / 'desktop/scripts/release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)

class ReleaseTests(unittest.TestCase):
    def guard(self, **changes):
        args = dict(version='0.2.0', confirmation='release desktop-v0.2.0 unsigned-prerelease', mode='unsigned-prerelease', rights_confirmed=True, repository='computerlovetech/umbod', ref='refs/heads/main', event='workflow_dispatch', expected_version='0.2.0')
        args.update(changes)
        return release.guard(**args)

    def test_explicit_desktop_dispatch(self):
        self.assertEqual(self.guard(), 'desktop-v0.2.0')

    def test_fail_closed(self):
        for changes in [dict(version='v0.2.0'), dict(version='0.2.0;id'), dict(version='01.2.0'), dict(version='0.2.0-beta'), dict(version='0.3.0'), dict(confirmation='yes'), dict(mode='production'), dict(mode='signed'), dict(rights_confirmed=False), dict(repository='someone/umbod'), dict(ref='refs/tags/desktop-v0.2.0'), dict(ref='refs/heads/feat/desktop-monorepo-releases'), dict(event='push')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.guard(**changes)

    def test_metadata_hashes_complete_and_exact(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ['Umbod-0.2.0-arm64.dmg', 'Umbod-0.2.0-release-win-x64.zip']:
                (folder / name).write_bytes(b'test artifact')
            manifest = release.metadata(folder, '0.2.0', 'a' * 40)
            self.assertEqual(manifest['tag'], 'desktop-v0.2.0')
            self.assertEqual(manifest['status'], 'available')
            self.assertEqual(set(manifest['assets']), {'macos-arm64', 'windows-x64'})
            for asset in manifest['assets'].values():
                self.assertEqual(asset['sha256'], hashlib.sha256(b'test artifact').hexdigest())
                self.assertIn('/computerlovetech/umbod/releases/download/desktop-v0.2.0/', asset['url'])
            self.assertIn('UNSIGNED', (folder/'RELEASE_NOTES.md').read_text())
            self.assertEqual(len((folder/'SHA256SUMS').read_text().splitlines()), 2)
            (folder/'Umbod-0.2.0-arm64.dmg').unlink()
            with self.assertRaises(ValueError): release.metadata(folder, '0.2.0', 'a'*40)

    def test_reject_invalid_provenance_empty_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaises(ValueError): release.metadata(folder, '0.2.0', 'main')
            (folder/'Umbod-0.2.0-arm64.dmg').write_bytes(b'')
            (folder/'Umbod-0.2.0-release-win-x64.zip').write_bytes(b'x')
            with self.assertRaises(ValueError): release.metadata(folder, '0.2.0', 'a'*40)
            (folder/'Umbod-0.2.0-arm64.dmg').unlink()
            (folder/'Umbod-0.2.0-arm64.dmg').symlink_to(folder/'Umbod-0.2.0-release-win-x64.zip')
            with self.assertRaises(ValueError): release.metadata(folder, '0.2.0', 'a'*40)

    def test_independent_version_and_safe_local_signing(self):
        version = (ROOT/'desktop/VERSION').read_text().strip()
        self.assertEqual(release.version(), version)
        build = (ROOT/'desktop/scripts/build.sh').read_text()
        self.assertNotIn('find-identity', build)
        self.assertIn('$VERSION', build)
        self.assertNotIn('Umbod 0.2.0', (ROOT/'desktop/windows/Umbod.Windows/MainWindow.cs').read_text())
        self.assertIn('ReadAllText', (ROOT/'desktop/windows/Directory.Build.props').read_text())
        self.assertIn('desktop/', (ROOT/'.dockerignore').read_text().splitlines())

    def test_native_smoke_default_from_monorepo_root(self):
        script = ROOT/'desktop/scripts/native-smoke.py'
        with mock.patch('sys.argv', [str(script)]), mock.patch('subprocess.Popen', side_effect=RuntimeError('do not launch')) as process:
            with self.assertRaisesRegex(RuntimeError, 'do not launch'):
                runpy.run_path(str(script))
        self.assertEqual(Path(process.call_args.args[0][0]), ROOT/'desktop/dist'/f'Umbod-{release.version()}.app/Contents/MacOS/Umbod')

    def test_existing_release_bytes(self):
        baseline = json.loads((ROOT/'desktop/tests/release-baseline.json').read_text())
        for file, digest in baseline.items():
            self.assertEqual(hashlib.sha256((ROOT/file).read_bytes()).hexdigest(), digest, file)

    def test_workflows_are_separate_and_guarded(self):
        workflow = (ROOT/'.github/workflows/desktop-release.yml').read_text()
        self.assertIn('workflow_dispatch:', workflow)
        self.assertNotIn('\n  push:', workflow)
        self.assertNotIn('\n  pull_request:', workflow)
        for required in ['release.py guard', 'needs: [guard, build]', '--prerelease', '--latest=false', '--verify-tag', 'desktop-release', 'website-manifest-update', 'rights_confirmed', 'persist-credentials: false']:
            self.assertIn(required, workflow)
        build = (ROOT/'.github/workflows/desktop-build.yml').read_text()
        for required in ['macos-15', 'windows-latest', 'cargo test --locked', 'UmbodTests', '--smoke-test', 'upload-artifact@', 'bun run build', 'test_release_workflow.py']:
            self.assertIn(required, build)

if __name__ == '__main__': unittest.main()
