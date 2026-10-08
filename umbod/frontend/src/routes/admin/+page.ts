import { error } from '@sveltejs/kit';
import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { loadAdminOverview } from '$lib/admin/overview/aggregate';
import { ApiOverviewSource } from '$lib/admin/overview/api-source';
import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  try {
    return { overview: await loadAdminOverview(new ApiOverviewSource(adminApi(event.fetch))) };
  } catch (loadError) {
    if (loadError instanceof HttpError && (loadError.status === 401 || loadError.status === 403)) {
      error(loadError.status, loadError.statusText);
    }
    throw loadError;
  }
};
