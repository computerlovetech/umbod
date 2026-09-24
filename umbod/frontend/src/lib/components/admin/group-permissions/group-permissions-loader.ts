import {
  connectorPermissionTargetSchema,
  groupPermissionSetSchema,
  type ConnectorPermissionTarget,
  type GroupPermissionSet
} from '$lib/admin/group-permissions';
import { BrowserRequestError, fetchResponse } from '$lib/admin/infrastructure/browser-request';

export interface GroupPermissionsLoader {
  loadGroup(groupId: string, signal?: AbortSignal): Promise<GroupPermissionSet>;
  loadAssignableTargets(signal?: AbortSignal): Promise<ConnectorPermissionTarget[]>;
}

export class BrowserGroupPermissionsLoader implements GroupPermissionsLoader {
  async loadGroup(groupId: string, signal?: AbortSignal): Promise<GroupPermissionSet> {
    const response = await fetchResponse(fetch, `/admin/group-permissions/data/groups/${encodeURIComponent(groupId)}`, { signal });
    if (!response.ok) throw new BrowserRequestError(response.status);
    return groupPermissionSetSchema.parse(await response.json());
  }

  async loadAssignableTargets(signal?: AbortSignal): Promise<ConnectorPermissionTarget[]> {
    const response = await fetchResponse(fetch, '/admin/group-permissions/data/assignable-targets', { signal });
    if (!response.ok) throw new BrowserRequestError(response.status);
    return connectorPermissionTargetSchema.array().parse(await response.json());
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
