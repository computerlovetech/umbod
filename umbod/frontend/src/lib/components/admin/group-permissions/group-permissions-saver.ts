import type { GroupPermissionSet, UpdateGroupPermissionsRequest } from '#lib/admin/group-permissions.js';
import { AdminApi } from '#lib/admin/infrastructure/admin-api.js';
import { browserRequest } from '#lib/admin/infrastructure/browser-request.js';
import { browserTransport } from '#lib/admin/infrastructure/transport.js';

export interface GroupPermissionsSaver {
  save(groupId: string, changes: UpdateGroupPermissionsRequest): Promise<GroupPermissionSet>;
}

export class BrowserGroupPermissionsSaver implements GroupPermissionsSaver {
  async save(groupId: string, changes: UpdateGroupPermissionsRequest): Promise<GroupPermissionSet> {
    const api = new AdminApi(browserTransport());
    return browserRequest(async () => {
      await api.groupPermissions.permissions.update(groupId, changes);
      return api.groupPermissions.permissions.get(groupId);
    });
  }
}
