import { error } from '@sveltejs/kit';
import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent }) => {
  await parent();
  const api = adminApi(fetch);
  try {
    const [agents, groups] = await Promise.all([api.agentTokens.list(), api.groups.list()]);
    return { agents, groups };
  } catch (failure) {
    if (failure instanceof HttpError) error(failure.status, failure.statusText);
    throw failure;
  }
};
