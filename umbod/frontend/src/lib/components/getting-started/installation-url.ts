export function normalizeInstallationUrl(value: string): string {
  if (!value || /[\s\u0000-\u001f\u007f\\${}]/u.test(value) || !/^https?:\/\//i.test(value)) {
    throw new Error('Use a literal HTTP or HTTPS installer URL without whitespace or placeholders.');
  }
  const authority = /^https?:\/\/([^/?#]+)/i.exec(value)?.[1];
  if (!authority) throw new Error('The installer URL requires a host.');
  const parsed = new URL(value);
  if (authority.includes('@') || parsed.username || parsed.password || value.includes('?') || value.includes('#')) {
    throw new Error('The installer URL must not contain credentials, a query, or a fragment.');
  }
  const hostname = authority.startsWith('[') ? authority.slice(0, authority.indexOf(']') + 1) : authority.split(':')[0];
  const loopback = hostname.toLowerCase() === 'localhost' ||
    (hostname.startsWith('[') && parsed.hostname === '[::1]') ||
    /^127\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})$/.test(hostname);
  if (parsed.protocol === 'http:' && !loopback) {
    throw new Error('Remote installer URLs require HTTPS.');
  }
  return parsed.href.replace(/\/+$/, '');
}

export function resolveInstallerBaseUrl(apiBaseUrl: string, pageUrl: URL): string {
  return normalizeInstallationUrl(new URL(`${apiBaseUrl.replace(/\/+$/, '')}/install/v1`, pageUrl).href);
}
