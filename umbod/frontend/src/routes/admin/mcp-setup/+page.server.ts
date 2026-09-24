import { runtimeConfigurationProvider } from '$lib/server/runtime-configuration';
import type { PageServerLoad } from './$types';

export type McpSetupPageData = {
  mcpEndpoint: string;
};

export const load: PageServerLoad = (): McpSetupPageData => {
  const publicMcpBaseUrl = runtimeConfigurationProvider().get().publicMcpBaseUrl.replace(/\/$/, '');
  return { mcpEndpoint: `${publicMcpBaseUrl}/mcp` };
};
