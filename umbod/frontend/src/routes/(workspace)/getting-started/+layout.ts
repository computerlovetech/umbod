import { publicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { resolveInstallerBaseUrl } from '$lib/components/getting-started/installation-url';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ url }) => {
  const configuration = await publicConfigurationProvider.get();
  return {
    installerBaseUrl: resolveInstallerBaseUrl(configuration.apiBaseUrl, url)
  };
};
