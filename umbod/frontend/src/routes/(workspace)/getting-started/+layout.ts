import { publicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';
import { resolveInstallerBaseUrl } from '#lib/components/getting-started/installation-url.js';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ url }) => {
  const configuration = await publicConfigurationProvider.get();
  return {
    installerBaseUrl: resolveInstallerBaseUrl(configuration.apiBaseUrl, url)
  };
};
