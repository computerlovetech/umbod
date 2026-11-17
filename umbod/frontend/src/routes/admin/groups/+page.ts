import { error } from '@sveltejs/kit';
import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => {
  try { return { groups: await adminApi(fetch).groups.list() }; }
  catch (failure) {
    if (failure instanceof HttpError && [401, 403].includes(failure.status)) error(failure.status, failure.statusText);
    throw failure;
  }
};
