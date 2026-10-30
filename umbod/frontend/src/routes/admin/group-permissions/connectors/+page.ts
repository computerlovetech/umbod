import { GroupPermissionsRouteState } from '$lib/components/admin/group-permissions/group-permissions-route-state.svelte';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ url }) => {
  const route = new GroupPermissionsRouteState(() => url);
  return { initialTarget: route.initialTarget, originHref: route.backHref };
};
