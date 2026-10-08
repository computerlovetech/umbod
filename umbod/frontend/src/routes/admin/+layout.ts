import { error } from '@sveltejs/kit';
import type { LayoutLoad } from './$types';
import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { createHeaderAccountUserInfoBoundary } from '$lib/header/accountIdentity';

export const load: LayoutLoad = async ({ fetch }) => {
  try {
    return { accountIdentity: createHeaderAccountUserInfoBoundary().viewHeaderAccountIdentity(await adminApi(fetch).currentUser()) };
  } catch (cause) {
    if (cause instanceof AuthenticationRequiredError) error(401, 'Your sign-in was not accepted by the API. Sign in again or contact your administrator.');
    if (cause instanceof HttpError) {
      if (cause.status === 403) error(403, 'You do not have permission to access this administration area. Contact your administrator.');
      error(cause.status, cause.statusText);
    }
    throw cause;
  }
};
