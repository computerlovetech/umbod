import { error } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import {
  deletePermissionGroup,
  loadGroupPermissions,
  registerPermissionGroup,
  updateGroupPermissions
} from '$lib/admin/group-permissions-api';
import { adminServerApi } from '$lib/admin/infrastructure/server-api';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { parseGroupIdFormValue, parsePermissionSetFormValue } from '$lib/admin/group-permissions-forms';
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

export const load: PageServerLoad = async (event) => {
  try {
    const data = await loadGroupPermissions(adminServerApi(event).groupPermissions);
    const requestUrl = event.url ?? new URL(event.request.url);
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

export const actions: Actions = {
  registerPermissionGroup: async ({ fetch, request }) => {
    const groupId = parseGroupIdFormValue((await request.formData()).get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    return registerPermissionGroup(adminServerApi({ fetch, request }).groupPermissions, groupId);
  },

  deletePermissionGroup: async ({ fetch, request }) => {
    const groupId = parseGroupIdFormValue((await request.formData()).get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    return deletePermissionGroup(adminServerApi({ fetch, request }).groupPermissions, groupId);
  },

  saveGroupPermissions: async ({ fetch, request }) => {
    const formData = await request.formData();
    const groupId = parseGroupIdFormValue(formData.get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    try {
      const permissionSet = parsePermissionSetFormValue(formData.get('permissionSet'), groupId);
      return updateGroupPermissions(adminServerApi({ fetch, request }).groupPermissions, groupId, permissionSet);
    } catch {
      return { status: 'rejected', groupId, message: 'Permission changes are invalid' };
    }
  }
};
