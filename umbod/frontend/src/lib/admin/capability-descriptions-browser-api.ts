import { CapabilityDescriptionConflictError, capabilityDescriptionResponseSchema, clearCapabilityDescriptionRequestSchema, revisionConflictEnvelopeSchema, setCapabilityDescriptionRequestSchema, type CapabilityDescriptionResponse, type ConnectorKind } from './capability-descriptions';
import { BrowserRequestError, fetchResponse } from './infrastructure/browser-request';

export class CapabilityDescriptionsBrowserRoute {
  constructor(private readonly request: typeof globalThis.fetch = globalThis.fetch) {}
  async get(kind: ConnectorKind, connectorId: string): Promise<CapabilityDescriptionResponse> { return this.call(kind, connectorId); }
  async set(kind: ConnectorKind, connectorId: string, description: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> { return this.call(kind, connectorId, setCapabilityDescriptionRequestSchema.parse({ action: 'set', description, expected_revision: expectedRevision })); }
  async clear(kind: ConnectorKind, connectorId: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> { return this.call(kind, connectorId, clearCapabilityDescriptionRequestSchema.parse({ action: 'clear', expected_revision: expectedRevision })); }
  private async call(kind: ConnectorKind, connectorId: string, body?: unknown): Promise<CapabilityDescriptionResponse> {
    const response = await fetchResponse(this.request, `/admin/connector-capability-descriptions/${kind}/${encodeURIComponent(connectorId)}`, body === undefined ? undefined : { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    const payload: unknown = await response.json();
    if (response.status === 409) {
      const conflict = revisionConflictEnvelopeSchema.parse(payload);
      throw new CapabilityDescriptionConflictError(conflict.detail.current);
    }
    if (!response.ok) throw new BrowserRequestError(response.status);
    return capabilityDescriptionResponseSchema.parse(payload);
  }
}
