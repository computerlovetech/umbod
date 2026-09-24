import { describe, expect, test } from 'vitest';
import { CapabilityDescriptionsRoute, CapabilityDescriptionConflictError } from './capability-descriptions-api';
import { capabilityDescriptionResponseSchema, revisionConflictEnvelopeSchema } from './capability-descriptions';
import type { Transport, TransportRequest } from './infrastructure/transport';

describe('capability description override contract', () => {
  test('parses discriminated system and overridden resolved states', () => {
    expect(capabilityDescriptionResponseSchema.parse({ connector_kind: 'native', connector_id: 'slack', base_description: 'System text', effective_description: 'System text', override: { state: 'system', revision: 0 } }).override.state).toBe('system');
    expect(capabilityDescriptionResponseSchema.parse({ connector_kind: 'openapi', connector_id: 'billing', base_description: 'Base', effective_description: 'Custom', override: { state: 'overridden', description: 'Custom', revision: 2 } }).override.state).toBe('overridden');
  });

  test('uses validated GET and PUT route payloads', async () => {
    const calls: TransportRequest<unknown>[] = [];
    const transport: Transport = { request: async <T>(request: TransportRequest<T>) => { calls.push(request as TransportRequest<unknown>); return {} as T; } };
    const route = new CapabilityDescriptionsRoute(transport);
    await route.get('downstream_mcp', 'payments');
    await route.set('downstream_mcp', 'payments', 'Custom', 3);
    await route.clear('downstream_mcp', 'payments', 4);
    expect(calls.map(({ method, path, body }) => ({ method, path, body }))).toEqual([
      { method: 'GET', path: '/admin/connector-capability-descriptions/downstream_mcp/payments', body: undefined },
      { method: 'PUT', path: '/admin/connector-capability-descriptions/downstream_mcp/payments', body: { action: 'set', description: 'Custom', expected_revision: 3 } },
      { method: 'PUT', path: '/admin/connector-capability-descriptions/downstream_mcp/payments', body: { action: 'clear', expected_revision: 4 } }
    ]);
  });

  test('decodes typed 409 current state', () => {
    const envelope = revisionConflictEnvelopeSchema.parse({ detail: { code: 'capability_description_revision_conflict', current: { connector_kind: 'native', connector_id: 'slack', base_description: 'Base', effective_description: 'New', override: { state: 'overridden', description: 'New', revision: 3 } } } });
    const error = new CapabilityDescriptionConflictError(envelope.detail.current);
    expect(error.current.override.revision).toBe(3);
  });
});
