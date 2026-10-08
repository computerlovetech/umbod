import { type BrowserOperations } from './contracts';

import { deletePermissionGroup, registerPermissionGroup, updateGroupPermissions } from '$lib/admin/group-permissions-api';

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

export const groupPermissionsOperations: BrowserOperations = {
  registerPermissionGroup: async (api, data) => {
    const groupId = parseGroupIdFormValue((data).get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    return registerPermissionGroup(api.groupPermissions, groupId);
  },

  deletePermissionGroup: async (api, data) => {
    const groupId = parseGroupIdFormValue((data).get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    return deletePermissionGroup(api.groupPermissions, groupId);
  },

  saveGroupPermissions: async (api, data) => {
    const groupId = parseGroupIdFormValue(data.get('groupId'));

    if (groupId === null) {
      return { status: 'rejected', groupId: '', message: 'Group value is required' };
    }

    try {
      const permissionSet = parsePermissionSetFormValue(data.get('permissionSet'), groupId);
      return updateGroupPermissions(api.groupPermissions, groupId, permissionSet);
    } catch {
      return { status: 'rejected', groupId, message: 'Permission changes are invalid' };
    }
  }
};
