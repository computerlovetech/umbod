import type { CapabilityDescriptionResponse, ConnectorKind } from './capability-descriptions';
import { adminApi } from './infrastructure/admin-api';
import { browserRequest } from './infrastructure/browser-request';

export class CapabilityDescriptionsBrowserRoute {
  constructor(private readonly request: typeof fetch = globalThis.fetch) {}
  get(kind: ConnectorKind, connectorId: string): Promise<CapabilityDescriptionResponse> {
    return browserRequest(() => adminApi(this.request).capabilityDescriptions.get(kind, connectorId));
  }
  set(kind: ConnectorKind, connectorId: string, description: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> {
    return browserRequest(() => adminApi(this.request).capabilityDescriptions.set(kind, connectorId, description, expectedRevision));
  }
  clear(kind: ConnectorKind, connectorId: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> {
    return browserRequest(() => adminApi(this.request).capabilityDescriptions.clear(kind, connectorId, expectedRevision));
  }
}
