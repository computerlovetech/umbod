import test from 'node:test';
import assert from 'node:assert/strict';
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const available = {
  schemaVersion: 1, status: 'available', version: '0.2.0', tag: 'desktop-v0.2.0',
  sourceCommit: 'a'.repeat(40), channel: 'unsigned-prerelease',
  assets: Object.fromEntries([
    ['macos-arm64', 'Umbod-0.2.0-arm64.dmg'],
    ['windows-x64', 'Umbod-0.2.0-release-win-x64.zip'],
  ].map(([platform, file]) => [platform, {
    url: `https://github.com/computerlovetech/umbod/releases/download/desktop-v0.2.0/${file}`,
    sha256: 'b'.repeat(64), size: 123,
  }])),
};

// Run the actual checkout checks against isolated website trees, never mutate the
// working manifest or recursively include this regression test in the child run.
for (const manifest of [{ schemaVersion: 1, status: 'unavailable' }, available]) {
  test(`website checks accept a checked-in ${manifest.status} manifest`, () => {
    const root = mkdtempSync(join(tmpdir(), 'umbod-manifest-state-'));
    try {
      for (const path of ['src', 'scripts', 'index.html']) {
        cpSync(new URL(`../${path}`, import.meta.url), join(root, path), { recursive: true });
      }
      mkdirSync(join(root, 'tests'));
      for (const file of ['downloads.test.mjs', 'manifest-update.test.mjs']) {
        cpSync(new URL(file, import.meta.url), join(root, 'tests', file));
      }
      mkdirSync(join(root, 'public'));
      writeFileSync(join(root, 'public/desktop-downloads.json'), JSON.stringify(manifest));
      const env = { ...process.env };
      delete env.NODE_TEST_CONTEXT;
      const result = spawnSync(process.execPath, ['--test', 'tests/downloads.test.mjs', 'tests/manifest-update.test.mjs'], {
        cwd: root, env, encoding: 'utf8', timeout: 30_000,
      });
      assert.ifError(result.error);
      assert.equal(result.status, 0, result.stdout + result.stderr);
    } finally {
      rmSync(root, { recursive: true, force: true });
    }
  });
}
