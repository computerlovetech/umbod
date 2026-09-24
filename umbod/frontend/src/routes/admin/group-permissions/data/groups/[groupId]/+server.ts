import { error, json, type RequestHandler } from '@sveltejs/kit';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { HttpError } from '$lib/admin/infrastructure/transport';

export const GET: RequestHandler = async (event) => {
  const groupId = event.params.groupId;
  if (groupId === undefined) error(400, 'Group ID is required');

  try {
    return json(await adminServerApi(event).groupPermissions.permissions.get(groupId));
  } catch (requestError) {
    if (requestError instanceof HttpError) error(requestError.status, requestError.statusText);
    throw requestError;
  }
};
