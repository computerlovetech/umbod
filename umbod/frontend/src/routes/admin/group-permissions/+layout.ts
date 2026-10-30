import { error } from '@sveltejs/kit';
import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { LayoutLoad } from './$types';

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    return { permissionGroups: await adminApi(fetch).groups.list() };
  } catch (cause) {
    if (cause instanceof HttpError && (cause.status === 401 || cause.status === 403)) error(cause.status, cause.statusText);
    throw cause;
  }
};
