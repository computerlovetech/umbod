import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, cpSync, mkdtempSync, mkdirSync, symlinkSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';

const root = fileURLToPath(new URL('../', import.meta.url));
const read = path => readFileSync(join(root, path), 'utf8');

test('home and enterprise have separate audiences and truthful product evidence', () => {
  const home = read('index.html');
  assert.match(home, /Your tools\. Your agents\./);
  assert.match(home, /Apple Silicon/);
  assert.match(home, /Windows.*x64/);
  assert.match(home, /connection diagram/i);
  assert.doesNotMatch(home, /tree\/main\/desktop/, 'desktop is not on main before this PR merges');
  assert.doesNotMatch(home, /kind create cluster|Grant access by group|umbod-overview\.mp4/);
  assert.ok(existsSync(join(root, 'enterprise/index.html')), 'enterprise is a real HTML entry');
  const enterprise = read('enterprise/index.html');
  assert.match(enterprise, /platform teams/i);
  assert.match(enterprise, /kind create cluster/);
  assert.match(enterprise, /Grant access by group/);
  assert.match(enterprise, /Kubernetes edition.*overview/i);
  assert.match(enterprise, /mailto:hello@computerlove\.tech/);
  assert.doesNotMatch(enterprise, /desktop-download-options|data-desktop-cta/);
});

for (const status of ['unavailable', 'available']) {
  test(`multi-page production build preserves routes, metadata, navigation and ${status} no-JS downloads`, async () => {
    const temporary = mkdtempSync(join(tmpdir(), 'umbod-pages-'));
    const site = join(temporary, 'website');
    mkdirSync(site);
    try {
      for (const path of ['index.html', 'enterprise', 'src', 'partials', 'styles.css', 'vite.config.js', 'wrangler.jsonc', 'package.json', 'public']) {
        assert.ok(existsSync(join(root, path)), `missing multi-page input: ${path}`);
        cpSync(join(root, path), join(site, path), { recursive: true });
      }
      cpSync(join(root, '../release-metadata.json'), join(temporary, 'release-metadata.json'));
      symlinkSync(join(root, 'node_modules'), join(site, 'node_modules'));
      const manifest = status === 'unavailable' ? {schemaVersion: 1, status} : {
        schemaVersion: 1, status, version: '0.2.0', tag: 'desktop-v0.2.0', sourceCommit: 'a'.repeat(40), channel: 'unsigned-prerelease',
        assets: Object.fromEntries([['macos-arm64', 'Umbod-0.2.0-arm64.dmg'], ['windows-x64', 'Umbod-0.2.0-release-win-x64.zip']].map(([platform, file]) => [platform, {url: `https://github.com/computerlovetech/umbod/releases/download/desktop-v0.2.0/${file}`, sha256: 'b'.repeat(64), size: 123}]))
      };
      writeFileSync(join(site, 'public/desktop-downloads.json'), JSON.stringify(manifest));
      const result = spawnSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build'], {cwd: site, encoding: 'utf8', timeout: 30000});
      assert.equal(result.status, 0, result.stdout + result.stderr);
      const pages = ['index.html', 'enterprise/index.html'].map(path => readFileSync(join(site, 'dist', path), 'utf8'));
      for (const [i, html] of pages.entries()) {
        const canonical = i ? 'https://umbod.ai/enterprise/' : 'https://umbod.ai/';
        assert.ok(html.includes(`<link rel="canonical" href="${canonical}">`));
        assert.ok(html.includes(`<meta property="og:url" content="${canonical}">`));
        assert.match(html, /href="\/enterprise\/"/);
        assert.match(html, /href="\/#downloads"/);
        assert.match(html, /href="\/docs\/"/);
        assert.match(html, /<noscript>/);
        assert.match(html, /<noscript>\s*<style>\.menu-toggle, \.copy-btn \{ display: none; \}<\/style>/, 'no inert controls without JavaScript');
        assert.doesNotMatch(html, /\{\{\s*(?:release|partial)\./);
        assert.equal((html.match(/<h1\b/g) || []).length, 1);
        for (const [, fragment] of html.matchAll(/href="#([^"]+)"/g)) assert.ok(html.includes(`id="${fragment}"`), `missing anchor ${fragment}`);
      }
      assert.notEqual(pages[0].match(/<title>(.*?)<\/title>/)[1], pages[1].match(/<title>(.*?)<\/title>/)[1]);
      assert.doesNotMatch(pages[1], /desktop-download-options|releases\/download/);
      if (status === 'available') {
        for (const asset of Object.values(manifest.assets)) assert.ok(pages[0].includes(asset.url));
        assert.match(pages[0], /Unsigned prerelease/);
        assert.match(pages[0], /SHA-256/);
      } else {
        assert.match(pages[0], /not available yet/);
        assert.doesNotMatch(pages[0], /releases\/download/);
      }
      const redirects = readFileSync(join(site, 'dist/_redirects'), 'utf8');
      assert.doesNotMatch(redirects, /\/enterprise\/?\s+\/\s+301/);
      assert.match(redirects, /\/enterprise\.html\s+\/enterprise\/\s+301/);
      if (status === 'unavailable') await verifyCloudflareRoutes(site);
    } finally { rmSync(temporary, {recursive: true, force: true}); }
  });
}

// Exercise the actual deployment runtime, not Vite's development SPA fallback.
async function verifyCloudflareRoutes(site) {
  const socket = createServer();
  await new Promise(resolve => socket.listen(0, '127.0.0.1', resolve));
  const port = socket.address().port;
  await new Promise(resolve => socket.close(resolve));
  const env = {...process.env, WRANGLER_SEND_METRICS: 'false'};
  delete env.NODE_TEST_CONTEXT;
  const worker = spawn(process.execPath, [join(root, 'node_modules/wrangler/bin/wrangler.js'), 'dev', '--local', '--ip', '127.0.0.1', '--port', String(port), '--inspector-port', '0'], {cwd: site, env, stdio: ['ignore', 'pipe', 'pipe']});
  let log = '';
  worker.stdout.on('data', data => { log += data; });
  worker.stderr.on('data', data => { log += data; });
  const base = `http://127.0.0.1:${port}`;
  try {
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { ready = (await fetch(base, {signal: AbortSignal.timeout(500)})).ok; } catch {}
      if (ready || worker.exitCode !== null) break;
      await delay(100);
    }
    assert.ok(ready, `Cloudflare runtime did not start: ${log}`);
    for (const path of ['/enterprise', '/enterprise/', '/enterprise.html']) {
      const response = await fetch(base + path, {signal: AbortSignal.timeout(5000)});
      assert.equal(response.status, 200, path);
      assert.equal(new URL(response.url).pathname, '/enterprise/', path);
      assert.match(await response.text(), /Umbod Enterprise/);
    }
    const missing = await fetch(base + '/not-a-real-page');
    assert.equal(missing.status, 404, 'unknown routes must not silently serve the desktop page');
    const home = await fetch(base + '/');
    assert.match(await home.text(), /Your tools\. Your agents\./);
  } finally {
    const exited = new Promise(resolve => worker.once('exit', resolve));
    if (worker.exitCode === null) { worker.kill('SIGTERM'); await exited; }
  }
}
