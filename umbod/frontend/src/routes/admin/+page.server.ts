import { error } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { loadAdminOverview } from '$lib/admin/overview/aggregate';
import { ApiOverviewSource } from '$lib/admin/overview/api-source';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async (event) => {
  try {
    return { overview: await loadAdminOverview(new ApiOverviewSource(adminServerApi(event))) };
  } catch (loadError) {
    if (loadError instanceof HttpError && (loadError.status === 401 || loadError.status === 403)) {
      error(loadError.status, loadError.statusText);
    }
    throw loadError;
  }
};
