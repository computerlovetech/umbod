import type { LayoutLoad } from './$types';
import { publicConfigurationProvider } from '#lib/admin/infrastructure/public-configuration.js';

export const ssr = false;
export const load: LayoutLoad = async () => {
  await publicConfigurationProvider.get();
  return { accountIdentity: { kind: 'hidden' as const } };
};
