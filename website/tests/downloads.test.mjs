import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { validateManifest, detectPlatform, selectDownload, loadManifest, renderDownloads } from '../src/downloads.mjs';
const fixture = () => ({ schemaVersion: 1, status: 'available', version: '0.2.0', tag: 'desktop-v0.2.0', sourceCommit: 'a'.repeat(40), channel: 'unsigned-prerelease', assets: Object.fromEntries([
  ['macos-arm64', 'Umbod-0.2.0-arm64.dmg'], ['windows-x64', 'Umbod-0.2.0-release-win-x64.zip'],
].map(([p, n]) => [p, { url: `https://github.com/computerlovetech/umbod/releases/download/desktop-v0.2.0/${n}`, sha256: 'b'.repeat(64), size: 123 }])) });

test('only exact desktop-specific manifests are accepted', () => {
  assert.equal(validateManifest(fixture()).version, '0.2.0');
  for (const change of [m => m.tag = 'v0.2.0', m => m.version = '01.2.0', m => m.version = '0.3.0', m => m.channel = 'stable', m => m.sourceCommit = 'main', m => m.status = 'draft', m => m.extra = true, m => delete m.assets['windows-x64'], m => m.assets.linux = {}, m => m.assets['macos-arm64'].size = -1, m => m.assets['macos-arm64'].sha256 = 'no', m => m.assets['windows-x64'].url = 'https://github.com/computerlovetech/umbod/releases/latest/download/app.zip', m => m.assets['macos-arm64'].url += '?token=private', m => m.assets['macos-arm64'].url = 'javascript:alert(1)', m => m.assets['macos-arm64'].url = m.assets['windows-x64'].url, m => m.assets['macos-arm64'].url = m.assets['macos-arm64'].url.replace('computerlovetech', 'attacker')]) {
    const m = fixture(); change(m); assert.throws(() => validateManifest(m));
  }
  for (const m of [null, [], {}, { schemaVersion: 1, status: 'unavailable', assets: {} }]) assert.throws(() => validateManifest(m));
  assert.deepEqual(validateManifest({ schemaVersion: 1, status: 'unavailable' }), { schemaVersion: 1, status: 'unavailable' });
});

test('platform hints never guess Apple Silicon from MacIntel or select mobile ARM', () => {
  assert.equal(detectPlatform({platform: 'macOS', architecture: 'arm', bitness: '64'}), 'macos-arm64');
  assert.equal(detectPlatform({platform: 'macOS', architecture: 'x86', bitness: '64'}), 'unsupported');
  assert.equal(detectPlatform({platform: 'Windows', architecture: 'x86', bitness: '64'}), 'windows-x64');
  assert.equal(detectPlatform({platform: 'Windows', architecture: 'arm', bitness: '64'}), 'unsupported');
  assert.equal(detectPlatform({}, 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'), 'macos-unknown');
  assert.equal(detectPlatform({}, 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'), 'windows-x64');
  for (const ua of ['Linux x86_64', 'iPhone', 'iPad Macintosh', 'Android', 'Windows NT 10.0; ARM64']) assert.equal(detectPlatform({}, ua), 'unsupported');
  assert.equal(detectPlatform({}, ''), 'unknown');
  assert.equal(detectPlatform({mobile: true, platform: 'macOS', architecture: 'arm', bitness: '64'}), 'unsupported');
});

test('download selection preserves manual choices and truthful unavailability', () => {
  assert.equal(selectDownload(fixture(), 'windows-x64').recommended, 'windows-x64');
  assert.equal(selectDownload(fixture(), 'macos-unknown').recommended, null);
  assert.equal(selectDownload(fixture(), 'unsupported').downloads.length, 2);
  assert.equal(selectDownload({schemaVersion: 1, status: 'unavailable'}, 'macos-arm64').downloads.length, 0);
  assert.equal(selectDownload(null, 'windows-x64').downloads.length, 0);
});

test('fetch fails closed for HTTP, network, malformed and redirected responses', async () => {
  for (const fetcher of [async () => { throw Error('offline'); }, async () => ({ok: false}), async () => ({ok: true, redirected: true}), async () => ({ok: true, json: async () => { throw Error('json'); }}), async () => ({ok: true, json: async () => ({tag: 'v1'})})]) assert.equal(await loadManifest(fetcher), null);
  assert.equal((await loadManifest(async (url, options) => { assert.equal(url, '/desktop-downloads.json'); assert.equal(options.credentials, 'omit'); return {ok: true, json: async () => fixture()}; })).tag, 'desktop-v0.2.0');
});

test('rendered links include explicit OS, unsigned label, version, hash and self-host path', () => {
  const html = renderDownloads(fixture(), 'windows-x64');
  for (const text of ['Windows x64', 'Apple Silicon', '0.2.0', 'Unsigned prerelease', 'SHA-256', 'b'.repeat(64), '/docs/getting-started/kubernetes-installation/', 'Recommended']) assert.ok(html.includes(text), text);
  const absent = renderDownloads(null, 'unknown');
  assert.ok(absent.includes('could not be verified'));
  assert.ok(renderDownloads({schemaVersion: 1, status: 'unavailable'}, 'unknown').includes('not available yet'));
  assert.ok(!absent.includes('releases/download'));
  assert.ok(absent.includes('/docs/getting-started/kubernetes-installation/'));
});

test('both CTAs target an accessible downloads section with no-JS fallback', () => {
  const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  assert.equal((html.match(/href="#downloads"/g) || []).length, 2);
  assert.ok(!html.includes('Try locally'));
  assert.ok(html.includes('id="downloads"'));
  assert.ok(html.includes('aria-labelledby="downloads-title"'));
  assert.ok(html.includes('aria-live="polite"'));
  assert.ok(html.includes('Desktop downloads are not available yet.'));
});

test('checked-in desktop manifest conforms to the supported schema', () => {
  const manifest = JSON.parse(readFileSync(new URL('../public/desktop-downloads.json', import.meta.url), 'utf8'));
  assert.doesNotThrow(() => validateManifest(manifest));
});
