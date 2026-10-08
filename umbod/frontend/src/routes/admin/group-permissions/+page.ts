import { error } from '@sveltejs/kit';
import { loadGroupPermissions } from '$lib/admin/group-permissions-api';
import { adminApi } from '$lib/admin/infrastructure/admin-api';
import { HttpError } from '$lib/admin/infrastructure/transport';

import { z } from 'zod';

const deepLinkValueSchema = z.string().min(1).max(200).regex(/^[^\u0000-\u001F\u007F]+$/);
const deepLinkQuerySchema = z.object({
  connector: deepLinkValueSchema,
  operation: deepLinkValueSchema
});

export type {
  ConnectorCapability,
  ConnectorPermissionTarget,
  ConnectorTool,
  GroupPermissionCapabilityRef,
  GroupPermissionSet,
  GroupPermissionToolRef,
  GroupPermissionsActionResult,
  GroupPermissionsPageData,
  SaveGroupPermissionsResult
} from '$lib/admin/group-permissions';

import type { PageLoad } from './$types';

export const load: PageLoad = async (event) => {
  try {
    const data = await loadGroupPermissions(adminApi(event.fetch).groupPermissions);
    const requestUrl = event.url;
    const query = deepLinkQuerySchema.safeParse({
      connector: requestUrl.searchParams.get('connector') ?? undefined,
      operation: requestUrl.searchParams.get('operation') ?? undefined
    });

    if (!query.success) {
      return data;
    }

    const connectorId = query.data.connector;
    const operationId = query.data.operation;
    const originHref = `/admin/openapi-connectors/${encodeURIComponent(connectorId)}`;

    return { ...data, initialTarget: { connectorId, operationId }, originHref };
  } catch (loadError) {
    if (loadError instanceof HttpError && (loadError.status === 401 || loadError.status === 403)) {
      error(loadError.status, loadError.statusText);
    }
    throw loadError;
  }
};

