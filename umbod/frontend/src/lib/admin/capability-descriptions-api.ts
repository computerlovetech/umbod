import { CapabilityDescriptionConflictError, capabilityDescriptionResponseSchema, clearCapabilityDescriptionRequestSchema, revisionConflictEnvelopeSchema, setCapabilityDescriptionRequestSchema, type CapabilityDescriptionResponse, type ConnectorKind } from './capability-descriptions';
import { HttpError, type Transport } from './infrastructure/transport';

export { CapabilityDescriptionConflictError } from './capability-descriptions';

export class CapabilityDescriptionsRoute {
  constructor(private readonly transport: Transport) {}

  get(kind: ConnectorKind, connectorId: string): Promise<CapabilityDescriptionResponse> {
    return this.transport.request({ method: 'GET', path: this.path(kind, connectorId), outputSchema: capabilityDescriptionResponseSchema });
  }

  set(kind: ConnectorKind, connectorId: string, description: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> {
    return this.put(kind, connectorId, { action: 'set', description, expected_revision: expectedRevision }, setCapabilityDescriptionRequestSchema);
  }

  clear(kind: ConnectorKind, connectorId: string, expectedRevision: number): Promise<CapabilityDescriptionResponse> {
    return this.put(kind, connectorId, { action: 'clear', expected_revision: expectedRevision }, clearCapabilityDescriptionRequestSchema);
  }

  private async put(kind: ConnectorKind, connectorId: string, body: unknown, inputSchema: typeof setCapabilityDescriptionRequestSchema | typeof clearCapabilityDescriptionRequestSchema): Promise<CapabilityDescriptionResponse> {
    try {
      return await this.transport.request({ method: 'PUT', path: this.path(kind, connectorId), body, inputSchema, outputSchema: capabilityDescriptionResponseSchema });
    } catch (error) {
      if (error instanceof HttpError && error.status === 409) {
        const parsed = revisionConflictEnvelopeSchema.safeParse(error.body);
        if (parsed.success) throw new CapabilityDescriptionConflictError(parsed.data.detail.current);
      }
      throw error;
    }
  }

  private path(kind: ConnectorKind, connectorId: string): string {
    return `/admin/connector-capability-descriptions/${kind}/${encodeURIComponent(connectorId)}`;
  }
}

