import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync, cpSync, mkdtempSync, mkdirSync, symlinkSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';

const root = fileURLToPath(new URL('../', import.meta.url));
const read = path => readFileSync(join(root, path), 'utf8');

const release = JSON.parse(read('../release-metadata.json'));
const retiredAssets = [
  'download/index.html',
  'src/downloads.mjs',
  'scripts/verify-desktop-manifest.mjs',
  'public/desktop-downloads.json',
  'public/oauth/client-metadata.json',
];

test('home and enterprise lead with Kubernetes onboarding and secondary contact', () => {
  for (const path of ['index.html', 'enterprise/index.html']) {
    const html = read(path);
    assert.match(html, /platform teams/i);
    assert.match(html, /kind create cluster/);
    assert.match(html, /Grant access by group/);
    assert.match(html, /Kubernetes edition.*overview/i);
    assert.match(html, /class="button" href="\/#how">Get started/);
    assert.match(html, /class="text-link" href="mailto:hello@computerlove\.tech/);
    assert.doesNotMatch(html, /Umbod Desktop|desktop-download-options|data-desktop-cta|Apple Silicon|Coming soon/);
  }
  assert.match(read('index.html'), /<title>Umbod — Agent access for platform teams<\/title>/);
  for (const path of retiredAssets) assert.ok(!existsSync(join(root, path)), path);
});

test('production build preserves routes, metadata, shared navigation and release versions', async () => {
  const temporary = mkdtempSync(join(tmpdir(), 'umbod-pages-'));
  const site = join(temporary, 'website');
  mkdirSync(site);
  try {
    for (const path of ['index.html', 'enterprise', 'src', 'partials', 'styles.css', 'vite.config.js', 'wrangler.jsonc', 'package.json', 'public']) {
      assert.ok(existsSync(join(root, path)), `missing multi-page input: ${path}`);
      cpSync(join(root, path), join(site, path), {recursive: true});
    }
    cpSync(join(root, '../release-metadata.json'), join(temporary, 'release-metadata.json'));
    symlinkSync(join(root, 'node_modules'), join(site, 'node_modules'));
    const result = spawnSync(process.execPath, [join(root, 'node_modules/vite/bin/vite.js'), 'build'], {cwd: site, encoding: 'utf8', timeout: 30000});
    assert.equal(result.status, 0, result.stdout + result.stderr);
    const pages = ['index.html', 'enterprise/index.html'].map(path => readFileSync(join(site, 'dist', path), 'utf8'));
    for (const [i, html] of pages.entries()) {
      const canonical = ['https://umbod.ai/', 'https://umbod.ai/enterprise/'][i];
      assert.ok(html.includes(`<link rel="canonical" href="${canonical}">`));
      assert.ok(html.includes(`<meta property="og:url" content="${canonical}">`));
      assert.doesNotMatch(html, /href="\/enterprise\/?"/);
      assert.match(html, /href="\/docs\/"/);
      const communityLinks = [...html.matchAll(/href="(https:\/\/discord\.gg\/[^\"]+)"/g)];
      assert.equal(communityLinks.length, 3);
      for (const [, href] of communityLinks) assert.equal(href, 'https://discord.gg/Njy4GnurpE');
      assert.match(html, /<noscript>\s*<style>\.menu-toggle, \.copy-btn \{ display: none; \}<\/style>/);
      for (const region of [
        html.match(/<nav class="wrap"[\s\S]*?<\/nav>/)[0],
        html.match(/<nav class="mobile-menu-links"[\s\S]*?<\/nav>/)[0],
        html.match(/<noscript>[\s\S]*?<\/noscript>/)[0],
        html.match(/<footer[\s\S]*?<\/footer>/)[0],
      ]) {
        assert.match(region, /href="\/#how">Get started/);
        assert.doesNotMatch(region, /download|desktop/i);
      }
      assert.doesNotMatch(html, /\{\{\s*(?:release|partial)\./);
      assert.doesNotMatch(html, /desktop-download-options|releases\/download|Umbod Desktop/);
      assert.equal((html.match(/<h1\b/g) || []).length, 1);
      assert.ok(html.includes(`--version ${release.chartVersion}`));
      assert.ok(html.includes(`${release.chartVersion} chart`));
      for (const [, fragment] of html.matchAll(/href="#([^"]+)"/g)) assert.ok(html.includes(`id="${fragment}"`), `missing anchor ${fragment}`);
    }
    assert.notEqual(pages[0].match(/<title>(.*?)<\/title>/)[1], pages[1].match(/<title>(.*?)<\/title>/)[1]);
    for (const path of ['download/index.html', 'desktop-downloads.json', 'oauth/client-metadata.json']) {
      assert.ok(!existsSync(join(site, 'dist', path)), path);
    }
    const redirects = readFileSync(join(site, 'dist/_redirects'), 'utf8');
    assert.doesNotMatch(redirects, /\/enterprise\/?\s+\/\s+301/);
    assert.match(redirects, /^\/enterprise\.html\s+\/enterprise\/\s+301$/m);
    assert.match(redirects, /^\/download\s+\/#how\s+301$/m);
    assert.match(redirects, /^\/download\/\s+\/#how\s+301$/m);
    await verifyCloudflareRoutes(site);
  } finally { rmSync(temporary, {recursive: true, force: true}); }
});

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
    for (const path of ['/download', '/download/']) {
      const redirect = await fetch(base + path, {redirect: 'manual'});
      assert.equal(redirect.status, 301);
      assert.equal(new URL(redirect.headers.get('location'), base).href, base + '/#how');
      const response = await fetch(base + path);
      assert.equal(response.status, 200);
      assert.equal(new URL(response.url).pathname, '/');
      assert.match(await response.text(), /kind create cluster/);
    }
    const missing = await fetch(base + '/not-a-real-page');
    assert.equal(missing.status, 404, 'unknown routes must not silently serve the home page');
    const home = await fetch(base + '/');
    assert.match(await home.text(), /Manage agent access\./);
  } finally {
    const exited = new Promise(resolve => worker.once('exit', resolve));
    if (worker.exitCode === null) { worker.kill('SIGTERM'); await exited; }
  }
}
