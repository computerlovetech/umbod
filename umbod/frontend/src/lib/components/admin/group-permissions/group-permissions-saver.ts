import type { GroupPermissionSet, UpdateGroupPermissionsRequest } from '$lib/admin/group-permissions';
import { AdminApi } from '$lib/admin/infrastructure/admin-api';
import { browserRequest } from '$lib/admin/infrastructure/browser-request';
import { browserTransport } from '$lib/admin/infrastructure/transport';

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
