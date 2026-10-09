const VERSION = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const SELF_HOST = '/docs/getting-started/kubernetes-installation/';
const PLATFORMS = {
  'macos-arm64': { label: 'macOS · Apple Silicon', requirements: 'macOS 14 or later. Ad-hoc signed; not notarized.', file: v => `Umbod-${v}-arm64.dmg` },
  'windows-x64': { label: 'Windows x64', requirements: 'Windows 10/11, x64. Unsigned, self-contained ZIP.', file: v => `Umbod-${v}-release-win-x64.zip` },
};
function exactKeys(value, keys) {
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join(',') !== [...keys].sort().join(',')) throw Error('Invalid desktop manifest shape');
}
export function validateManifest(m) {
  if (m?.status === 'unavailable') {
    exactKeys(m, ['schemaVersion', 'status']);
    if (m.schemaVersion !== 1) throw Error('Unsupported manifest schema');
    return m;
  }
  exactKeys(m, ['schemaVersion', 'status', 'version', 'tag', 'sourceCommit', 'channel', 'assets']);
  if (m.schemaVersion !== 1 || m.status !== 'available' || typeof m.version !== 'string' || !VERSION.test(m.version) || m.tag !== `desktop-v${m.version}` || m.channel !== 'unsigned-prerelease' || !/^[a-f0-9]{40}$/.test(m.sourceCommit)) throw Error('Invalid desktop release');
  exactKeys(m.assets, Object.keys(PLATFORMS));
  for (const [platform, info] of Object.entries(PLATFORMS)) {
    const asset = m.assets[platform];
    exactKeys(asset, ['url', 'sha256', 'size']);
    const expected = `https://github.com/computerlovetech/umbod/releases/download/${m.tag}/${info.file(m.version)}`;
    if (asset.url !== expected || typeof asset.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(asset.sha256) || !Number.isSafeInteger(asset.size) || asset.size <= 0) throw Error('Invalid desktop asset');
  }
  return m;
}
export function detectPlatform(hints = {}, userAgent = '') {
  if (hints.mobile || /Android|iPhone|iPad|iPod/i.test(userAgent)) return 'unsupported';
  const os = (hints.platform || '').toLowerCase();
  if (os === 'macos' && hints.architecture) return hints.architecture === 'arm' && hints.bitness === '64' ? 'macos-arm64' : 'unsupported';
  if (os === 'windows' && hints.architecture) return hints.architecture === 'x86' && hints.bitness === '64' ? 'windows-x64' : 'unsupported';
  if (/Windows.*ARM/i.test(userAgent)) return 'unsupported';
  if (/Windows.*(Win64|WOW64|x64)/i.test(userAgent)) return 'windows-x64';
  if (os === 'macos' || /Macintosh|MacIntel/i.test(userAgent)) return 'macos-unknown';
  if (os === 'windows') return 'unknown';
  if (/Linux|CrOS|Windows/i.test(userAgent) || ['android', 'ios', 'linux', 'chrome os'].includes(os)) return 'unsupported';
  return 'unknown';
}
export function selectDownload(manifest, platform) {
  try {
    const m = validateManifest(manifest);
    if (m.status !== 'available') return { recommended: null, downloads: [] };
    return { recommended: Object.hasOwn(PLATFORMS, platform) ? platform : null,
      downloads: Object.entries(PLATFORMS).map(([id, info]) => ({id, ...info, ...m.assets[id], version: m.version})) };
  } catch { return { recommended: null, downloads: [] }; }
}
export async function loadManifest(fetcher = globalThis.fetch) {
  try {
    const response = await fetcher('/desktop-downloads.json', { credentials: 'omit', redirect: 'error', cache: 'no-cache', signal: AbortSignal.timeout(5000) });
    if (!response.ok || response.redirected) return null;
    return validateManifest(await response.json());
  } catch { return null; }
}
export function renderDownloads(manifest, platform) {
  const {recommended, downloads} = selectDownload(manifest, platform);
  const alternative = `<p class="download-alternative"><a class="text-link" href="${SELF_HOST}">Self-host on Kubernetes <span aria-hidden="true">↗</span></a></p>`;
  if (!downloads.length) {
    let message = 'Desktop downloads could not be verified. Please try again, or self-host Umbod today.';
    try { if (validateManifest(manifest).status === 'unavailable') message = 'Desktop downloads are not available yet. You can self-host Umbod today.'; } catch {}
    return `<p>${message}</p>` + alternative;
  }
  // All interpolated values are fixed strings or validated version/hash/allowlisted URLs.
  return '<p>Unsigned prerelease · ' + downloads[0].version + '. Do not disable system security to run it.</p>' +
    (platform === 'unsupported' ? '<p>No native download is available for your platform. Builds for other computers are listed below.</p>' : platform === 'macos-unknown' ? '<p>Choose the Apple Silicon build only if your Mac has an Apple M-series chip. Intel Macs are not supported.</p>' : '') +
    '<div class="download-grid">' + downloads.map(d => `<article class="download-card"><h3>${d.label}${d.id === recommended ? ' · Recommended' : ''}</h3><p>${d.requirements}</p><a class="button" href="${d.url}">Download for ${d.label} <span aria-hidden="true">↓</span></a><details><summary>Verify download · SHA-256</summary><code>${d.sha256}</code></details></article>`).join('') + '</div>' + alternative;
}
export async function initializeDownloads(doc = document, nav = navigator) {
  const container = doc.getElementById('desktop-download-options');
  if (!container) return;
  let hints = nav.userAgentData || {};
  try {
    if (hints.getHighEntropyValues) hints = await Promise.race([
      hints.getHighEntropyValues(['platform', 'architecture', 'bitness', 'mobile']),
      new Promise(resolve => setTimeout(() => resolve({}), 1000)),
    ]);
  } catch { hints = {}; }
  // iPadOS can expose a Mac UA; do not recommend a Mac binary for a touch tablet.
  if (nav.maxTouchPoints > 1 && /Macintosh/i.test(nav.userAgent)) hints = {mobile: true};
  const platform = detectPlatform(hints, nav.userAgent);
  const manifest = await loadManifest();
  container.innerHTML = renderDownloads(manifest, platform);
  const selection = selectDownload(manifest, platform);
  if (selection.downloads.length) {
    for (const cta of doc.querySelectorAll('[data-desktop-cta]')) {
      cta.textContent = selection.recommended ? `Download for ${PLATFORMS[selection.recommended].label}` : 'Download desktop';
    }
  }
}

export function renderDesktopPage(html, manifest) {
  validateManifest(manifest);
  const start = '<!-- desktop-downloads:start -->';
  const end = '<!-- desktop-downloads:end -->';
  if (!html.includes(start) || !html.includes(end)) throw Error('Missing desktop HTML boundaries');
  return html.slice(0, html.indexOf(start) + start.length) + renderDownloads(manifest, 'unknown') + html.slice(html.indexOf(end));
}
