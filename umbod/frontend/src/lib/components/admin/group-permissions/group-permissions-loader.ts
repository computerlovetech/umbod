import { type ConnectorPermissionTarget, type GroupPermissionSet } from '$lib/admin/group-permissions';
import { browserRequest } from '$lib/admin/infrastructure/browser-request';
import { AdminApi } from '$lib/admin/infrastructure/admin-api';
import { browserTransport } from '$lib/admin/infrastructure/transport';

export interface GroupPermissionsLoader {
  loadGroup(groupId: string, signal?: AbortSignal): Promise<GroupPermissionSet>;
  loadAssignableTargets(signal?: AbortSignal): Promise<ConnectorPermissionTarget[]>;
}

export class BrowserGroupPermissionsLoader implements GroupPermissionsLoader {
  async loadGroup(groupId: string, signal?: AbortSignal): Promise<GroupPermissionSet> {
    return browserRequest(() => this.api(signal).groupPermissions.permissions.get(groupId));
  }

  async loadAssignableTargets(signal?: AbortSignal): Promise<ConnectorPermissionTarget[]> {
    return browserRequest(() => this.api(signal).groupPermissions.permissions.listAssignableTargets());
  }

  private api(signal?: AbortSignal): AdminApi {
    const transport = browserTransport();
    return new AdminApi({ request: (options) => transport.request({ ...options, signal }) });
  }
}

export class InMemoryGroupPermissionsLoader implements GroupPermissionsLoader {
  constructor(
    private readonly groups: Map<string, GroupPermissionSet>,
    private readonly targets: ConnectorPermissionTarget[]
  ) {}

  async loadGroup(groupId: string): Promise<GroupPermissionSet> {
    const group = this.groups.get(groupId);
    if (group === undefined) throw new Error(`Unknown group ${groupId}`);
    return structuredClone(group);
  }

  async loadAssignableTargets(): Promise<ConnectorPermissionTarget[]> {
    return structuredClone(this.targets);
  }
}
