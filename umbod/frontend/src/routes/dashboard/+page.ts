import { publicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import type { PageLoad } from './$types';

export const load: PageLoad = async () => {
  const configuration = await publicConfigurationProvider.get();
  return { mcpEndpoint: `${configuration.mcpBaseUrl.replace(/\/$/, '')}/mcp` };
};
