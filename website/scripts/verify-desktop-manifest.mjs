#!/usr/bin/env node
// Maintainer tool: anonymous public verification; never uses GH_TOKEN or browser credentials.
import { createHash } from 'node:crypto';
import { readFile, writeFile, rename } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { validateManifest } from '../src/downloads.mjs';

export async function verifyPublicRelease(manifest, fetcher = globalThis.fetch) {
  const m = validateManifest(manifest);
  if (m.status !== 'available') throw Error('Expected a released desktop manifest');
  const options = () => ({ credentials: 'omit', signal: AbortSignal.timeout(300000) });
  async function json(url) {
    const response = await fetcher(url, options());
    if (!response.ok) throw Error('Public release verification failed');
    return response.json();
  }
  const base = 'https://api.github.com/repos/computerlovetech/umbod';
  const release = await json(`${base}/releases/tags/${m.tag}`);
  if (release.tag_name !== m.tag || release.draft !== false || release.prerelease !== true || !Array.isArray(release.assets)) throw Error('Expected the exact published unsigned prerelease');
  const ref = await json(`${base}/git/ref/tags/${m.tag}`);
  if (ref.object?.type !== 'commit' || ref.object.sha !== m.sourceCommit) throw Error('Release tag source does not match manifest');
  for (const asset of Object.values(m.assets)) {
    const published = release.assets.filter(a => a.browser_download_url === asset.url);
    if (published.length !== 1 || published[0].state !== 'uploaded' || published[0].size !== asset.size) throw Error('Missing or mismatched public asset');
    const response = await fetcher(asset.url, options());
    if (!response.ok || !response.body) throw Error('Public download unavailable');
    const hash = createHash('sha256');
    let bytes = 0;
    for await (const chunk of response.body) {
      bytes += chunk.length;
      if (bytes > asset.size) throw Error('Asset exceeds recorded size');
      hash.update(chunk);
    }
    if (bytes !== asset.size || hash.digest('hex') !== asset.sha256) throw Error('Public asset checksum mismatch');
  }
  return m;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const [input, flag] = process.argv.slice(2);
    if (!input || (flag && flag !== '--apply')) throw Error('Usage: node website/scripts/verify-desktop-manifest.mjs manifest.json [--apply]');
    const manifest = await verifyPublicRelease(JSON.parse(await readFile(input, 'utf8')));
    if (flag === '--apply') {
      const target = new URL('../public/desktop-downloads.json', import.meta.url);
      const temporary = new URL('../public/.desktop-downloads.json.tmp', import.meta.url);
      await writeFile(temporary, JSON.stringify(manifest, null, 2) + '\n', {flag: 'wx'});
      await rename(temporary, target);
      console.log('Verified and applied desktop manifest. Review the diff and open a PR.');
    } else console.log('Verified public desktop release and both artifact hashes; no files changed.');
  } catch (error) { console.error(error.message); process.exitCode = 1; }
}
