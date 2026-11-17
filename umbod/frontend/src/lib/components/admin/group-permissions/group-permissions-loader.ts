import { type ConnectorPermissionTarget, type GroupPermissionSet } from '#lib/admin/group-permissions.js';
import { browserRequest } from '#lib/admin/infrastructure/browser-request.js';
import { AdminApi } from '#lib/admin/infrastructure/admin-api.js';
import { browserTransport } from '#lib/admin/infrastructure/transport.js';

export type ConnectorPresentationSummary = {
  id: string;
  displayName: string;
  publicationStatus: 'published' | 'unpublished';
};

export interface GroupPermissionsLoader {
  loadConnectorSummaries(signal?: AbortSignal): Promise<ConnectorPresentationSummary[]>;
  loadGroup(groupId: string, signal?: AbortSignal): Promise<GroupPermissionSet>;
  loadAssignableTargets(signal?: AbortSignal): Promise<ConnectorPermissionTarget[]>;
}

export class BrowserGroupPermissionsLoader implements GroupPermissionsLoader {
  async loadConnectorSummaries(signal?: AbortSignal): Promise<ConnectorPresentationSummary[]> {
    const inventory = await browserRequest(() => this.api(signal).downstreamMcpConnectors.list());
    return inventory.connectors.map((connector) => ({
      id: connector.connector_id,
      displayName: connector.display_name,
      publicationStatus: connector.publication_status
    }));
  }

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
    private readonly targets: ConnectorPermissionTarget[],
    private readonly summaries: ConnectorPresentationSummary[] = []
  ) {}

  async loadConnectorSummaries(): Promise<ConnectorPresentationSummary[]> {
    return structuredClone(this.summaries);
  }

  async loadGroup(groupId: string): Promise<GroupPermissionSet> {
    const group = this.groups.get(groupId);
    if (group === undefined) throw new Error(`Unknown group ${groupId}`);
    return structuredClone(group);
  }

  async loadAssignableTargets(): Promise<ConnectorPermissionTarget[]> {
    return structuredClone(this.targets);
  }
}
