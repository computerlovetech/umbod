import { publicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import type { PageLoad } from './$types';

export type McpSetupPageData = { mcpEndpoint: string };
export const load: PageLoad = async (): Promise<McpSetupPageData> => {
  const configuration = await publicConfigurationProvider.get();
  return { mcpEndpoint: `${configuration.mcpBaseUrl.replace(/\/$/, '')}/mcp` };
};
