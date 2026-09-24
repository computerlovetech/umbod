import { describe, expect, test, vi } from 'vitest';
import { load } from './+page.server';
import { GroupPermissionsState, type GroupPermissionsInitialData } from '$lib/components/admin/group-permissions/group-permissions-state.svelte';
import { InMemoryGroupPermissionsLoader } from '$lib/components/admin/group-permissions/group-permissions-loader';

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });
}

function event(url: string, fetch: typeof globalThis.fetch): Parameters<typeof load>[0] {
  const request = new Request(url);
  return { fetch, request, url: new URL(url) } as Parameters<typeof load>[0];
}

const connectorId = 'inventory/eu';
const operationId = 'list items';
const fetch = vi.fn(async (input: string | URL | Request) => {
  const path = String(input);
  if (path.endsWith('/groups')) return response({ groups: [{ group_id: 'engineering' }] });
  if (path.endsWith('/groups/engineering')) {
    return response({
      group_id: 'engineering',
      connector_ids: [connectorId],
      capabilities: [{ connector_id: connectorId, capability_kind: 'tool', capability_key: 'getItem' }]
    });
  }
  return response({
    connectors: [{ connector_id: connectorId, display_name: 'Inventory EU' }],
    capabilities: [
      { connector_id: connectorId, capability_kind: 'tool', capability_key: operationId, display_name: 'List items' },
      { connector_id: connectorId, capability_kind: 'tool', capability_key: 'getItem', display_name: 'Get item' }
    ]
  });
});

function loader(): InMemoryGroupPermissionsLoader {
  return new InMemoryGroupPermissionsLoader(
    new Map([['engineering', {
      groupId: 'engineering',
      connectorIds: [connectorId],
      capabilities: [{ connectorId, kind: 'tool', key: 'getItem' }]
    }]]),
    [{
      id: connectorId,
      displayName: 'Inventory EU',
      description: '',
      capabilities: [
        { kind: 'tool', key: operationId, label: 'List items', description: '' },
        { kind: 'tool', key: 'getItem', label: 'Get item', description: '' }
      ]
    }]
  );
}

describe('OpenAPI operation permission deep links', () => {
  test('maps validated query parameters to initial selection without granting', async () => {
    const data = await load(event(`http://frontend/admin/group-permissions?connector=${encodeURIComponent(connectorId)}&operation=${encodeURIComponent(operationId)}`, fetch as never));
    expect(data).toMatchObject({ initialTarget: { connectorId, operationId }, originHref: '/admin/openapi-connectors/inventory%2Feu' });

    const state = new GroupPermissionsState(data as GroupPermissionsInitialData, null, null, loader());
    expect(state.selectedGroupId).toBe('engineering');
    expect(state.editorStatus).toBe('ready');
    expect(state.expandedConnectorId).toBe(connectorId);
    expect(state.selectedOperationId).toBe(operationId);
    expect(state.hasUnsavedChanges).toBe(false);
  });

  test('marks a stale target unavailable and never fabricates it', async () => {
    const data = await load(event(`http://frontend/admin/group-permissions?connector=${encodeURIComponent(connectorId)}&operation=removed`, fetch as never));
    const state = new GroupPermissionsState(data as GroupPermissionsInitialData, null, null, loader());
    expect(state.deepLinkedTargetAvailable).toBe(false);
    expect(state.connectors.flatMap((connector) => connector.capabilities.map((capability) => capability.key))).not.toContain('removed');
  });

  test('maps existing OpenAPI grants and stages an exact operation change', async () => {
    const data = await load(event(`http://frontend/admin/group-permissions?connector=${encodeURIComponent(connectorId)}&operation=${encodeURIComponent(operationId)}`, fetch as never));
    const state = new GroupPermissionsState(data as GroupPermissionsInitialData, null, null, loader());

    expect(state.connectorIsGranted(connectorId)).toBe(true);
    expect(state.toolIsGranted({ connectorId, operationName: 'getItem' })).toBe(true);
    expect(state.toolIsGranted({ connectorId, operationName: operationId })).toBe(false);

    state.setToolPermission({ connectorId, operationName: operationId }, true);

    expect(state.hasUnsavedChanges).toBe(true);
    expect(JSON.parse(state.selectedPermissionSetJson)).toEqual({
      groupId: 'engineering',
      connectorIds: [connectorId],
      capabilities: [
        { connectorId, kind: 'tool', key: 'getItem' },
        { connectorId, kind: 'tool', key: operationId }
      ]
    });
  });

  test('rejects incomplete query selections', async () => {
    const data = await load(event('http://frontend/admin/group-permissions?connector=orders', fetch as never));
    expect(data).toMatchObject({ initialTarget: null, originHref: null });
  });
});
