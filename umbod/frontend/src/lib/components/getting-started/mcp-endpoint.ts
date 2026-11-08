export function resolveMcpEndpoint(baseUrl: string, siteUrl: URL): string {
  const endpoint = new URL(baseUrl, siteUrl.origin);
  const path = endpoint.pathname.replace(/\/+$/, '');
  endpoint.pathname = path.endsWith('/mcp') ? path : `${path}/mcp`;
  return endpoint.href;
}
