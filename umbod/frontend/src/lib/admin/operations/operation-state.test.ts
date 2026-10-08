import { describe, expect, test } from 'vitest';
import { OperationState } from './operation-state.svelte';

describe('submission feedback ownership', () => {
  test('does not expose one connector configuration to another connector or workspace', () => {
    const state = new OperationState();
    state.replace({ status: 'failed', values: { host: 'billing.example.test' } }, { route: '/admin/connectors', connectorId: 'billing' });
    expect(state.forOwner({ route: '/admin/connectors', connectorId: 'billing' })).toMatchObject({ status: 'failed' });
    expect(state.forOwner({ route: '/admin/connectors', connectorId: 'other' })).toBeNull();
    expect(state.forOwner({ route: '/admin/openapi-connectors', connectorId: 'billing' })).toBeNull();
  });
  test('clears feedback when the navigation location changes', () => {
    const state = new OperationState();
    state.resetForPath('/admin/connectors?connector=billing');
    state.replace({ status: 'failed' }, { route: '/admin/connectors', connectorId: 'billing' });
    state.resetForPath('/admin/connectors?connector=other');
    expect(state.data).toBeNull();
  });
});
