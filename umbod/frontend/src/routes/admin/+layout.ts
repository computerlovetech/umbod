import { error } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';
import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { createHeaderAccountUserInfoBoundary } from '$lib/header/accountIdentity';

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    return { accountIdentity: createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(await adminApi(fetch).currentUser()) };
  } catch (cause) {
    if (cause instanceof HttpError) error(cause.status, cause.statusText);
    throw cause;
  }
};
