import { error, json, type RequestHandler } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { HttpError } from '$lib/admin/infrastructure/transport';

export const GET: RequestHandler = async (event) => {
  try {
    return json(await adminServerApi(event).groupPermissions.permissions.listAssignableTargets());
  } catch (requestError) {
    if (requestError instanceof HttpError) error(requestError.status, requestError.statusText);
    throw requestError;
  }
};
