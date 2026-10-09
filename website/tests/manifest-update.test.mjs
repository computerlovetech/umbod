import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { verifyPublicRelease } from '../scripts/verify-desktop-manifest.mjs';
import { renderDesktopPage } from '../src/downloads.mjs';
const body = Buffer.from('published fixture');
const manifest = { schemaVersion: 1, status: 'available', version: '0.2.0', tag: 'desktop-v0.2.0', sourceCommit: 'a'.repeat(40), channel: 'unsigned-prerelease', assets: Object.fromEntries(['macos-arm64', 'windows-x64'].map((p, i) => [p, {url: `https://github.com/computerlovetech/umbod/releases/download/desktop-v0.2.0/${i ? 'Umbod-0.2.0-release-win-x64.zip' : 'Umbod-0.2.0-arm64.dmg'}`, sha256: createHash('sha256').update(body).digest('hex'), size: body.length}])) };
const release = () => ({tag_name: manifest.tag, draft: false, prerelease: true, assets: Object.values(manifest.assets).map(a => ({browser_download_url: a.url, size: a.size, state: 'uploaded'}))});
function fetcher(metadata = release(), bytes = body, sha = manifest.sourceCommit) {
  return async (url, options) => {
    assert.equal(options.credentials, 'omit');
    if (url.includes('/releases/tags/')) return {ok: true, json: async () => metadata};
    if (url.includes('/git/ref/tags/')) return {ok: true, json: async () => ({object: {type: 'commit', sha}})};
    return {ok: true, body: (async function* () {yield bytes;})()};
  };
}
test('application requires public release, exact tag source, sizes and downloaded hashes', async () => {
  await verifyPublicRelease(manifest, fetcher());
  for (const r of [{...release(), draft: true}, {...release(), tag_name:'v0.2.0'}, {...release(), prerelease:false}, {...release(), assets:[]}]) await assert.rejects(verifyPublicRelease(manifest, fetcher(r)));
  await assert.rejects(verifyPublicRelease(manifest, fetcher(release(), Buffer.from('bad'))));
  await assert.rejects(verifyPublicRelease(manifest, fetcher(release(), body, 'b'.repeat(40))));
  await assert.rejects(verifyPublicRelease(manifest, async () => ({ok: false})));
});
test('static HTML follows manifest for no-JavaScript visitors', () => {
  const html = '<div><!-- desktop-downloads:start -->old<!-- desktop-downloads:end --></div>';
  assert.ok(renderDesktopPage(html, manifest).includes('Download for Windows x64'));
  assert.ok(!renderDesktopPage(html, manifest).includes('>old<'));
  assert.ok(renderDesktopPage(html, {schemaVersion: 1, status:'unavailable'}).includes('not available'));
  assert.throws(() => renderDesktopPage(html, {status: 'available'}));
});
