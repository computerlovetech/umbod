import { publicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { resolveMcpEndpoint } from '$lib/components/getting-started/mcp-endpoint';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ url }) => {
  const configuration = await publicConfigurationProvider.get();
  return { mcpEndpoint: resolveMcpEndpoint(configuration.mcpBaseUrl, url) };
};
