import { describe, expect, test, vi } from 'vitest';
import { serverTransport, type Transport, type TransportRequest } from './infrastructure/transport';
import {
  GroupPermissionsApi,
  deletePermissionGroup,
  loadGroupPermissions,
  registerPermissionGroup,
  updateGroupPermissions
} from './group-permissions-api';
import { permissionSetDifference, updateGroupPermissionsRequestSchema } from './group-permissions';

function recordingTransport(): { transport: Transport; calls: TransportRequest<unknown>[] } {
  const calls: TransportRequest<unknown>[] = [];
  const transport: Transport = {
    async request(opts) {
      calls.push(opts as TransportRequest<unknown>);
      if (opts.path.endsWith('/assignable-targets')) return { connectors: [], capabilities: [] } as never;
      if (opts.path === '/admin/mcp-permissions/groups') return { groups: [] } as never;
      if (opts.method === 'GET') return { group_id: 'team a', connector_ids: [], capabilities: [] } as never;
      return undefined as never;
    }
  };
  return { transport, calls };
}

function apiFromFetch(fetch: ReturnType<typeof vi.fn>): GroupPermissionsApi {
  return new GroupPermissionsApi(serverTransport(fetch as unknown as typeof globalThis.fetch));
}

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init
  });
}

describe('GroupPermissionsApi route contracts', () => {
  test('list, get, and listAssignableTargets target the admin endpoints', () => {
    const { transport, calls } = recordingTransport();
    const api = new GroupPermissionsApi(transport);
    void api.permissions.list();
    void api.permissions.get('team a');
    void api.permissions.listAssignableTargets();

    expect(calls[0]).toMatchObject({ method: 'GET', path: '/admin/mcp-permissions/groups' });
    expect(calls[1]).toMatchObject({ method: 'GET', path: '/admin/mcp-permissions/groups/team%20a' });
    expect(calls[2]).toMatchObject({ method: 'GET', path: '/admin/mcp-permissions/assignable-targets' });
  });

  test('register and delete encode the group id', () => {
    const { transport, calls } = recordingTransport();
    const api = new GroupPermissionsApi(transport);
    api.permissions.register('team a');
    api.permissions.delete('team a');

    expect(calls[0]).toMatchObject({ method: 'POST', path: '/admin/mcp-permissions/groups/team%20a' });
    expect(calls[1]).toMatchObject({ method: 'DELETE', path: '/admin/mcp-permissions/groups/team%20a' });
  });

  test('update PUTs only changed permissions to the partial endpoint', () => {
    const { transport, calls } = recordingTransport();
    const changes = { connectors: [{ connector_id: 'c1', permission_status: 'disabled' as const }], capabilities: [] };
    new GroupPermissionsApi(transport).permissions.update('g1', changes);

    expect(calls[0]).toMatchObject({
      method: 'PUT',
      path: '/admin/mcp-permissions/groups/g1/permissions',
      body: changes
    });
    expect(calls[0].inputSchema).toBe(updateGroupPermissionsRequestSchema);
  });
});

describe('loadGroupPermissions', () => {
  test('loads summaries before preloading the first group and targets', async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path.endsWith('/groups')) return jsonResponse({ groups: [{ group_id: 'g1' }, { group_id: 'g2' }] });
      if (path.endsWith('/groups/g1')) return jsonResponse({ group_id: 'g1', connector_ids: [], capabilities: [] });
      return jsonResponse({ connectors: [], capabilities: [] });
    });

    const data = await loadGroupPermissions(apiFromFetch(fetch));

    expect(data.groups).toEqual([{ groupId: 'g1' }, { groupId: 'g2' }]);
    expect(data.preloadedGroup).toEqual({ groupId: 'g1', connectorIds: [], capabilities: [] });
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(String(fetch.mock.calls[0]?.[0])).toMatch(/\/groups$/);
  });

  test('does not load detail or targets when there are no groups', async () => {
    const fetch = vi.fn(async () => jsonResponse({ groups: [] }));

    await expect(loadGroupPermissions(apiFromFetch(fetch))).resolves.toMatchObject({ preloadedGroup: null, assignableTargets: [] });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe('registerPermissionGroup', () => {
  test('returns registered on success', async () => {
    const fetch = vi.fn(async () => jsonResponse({}));
    await expect(registerPermissionGroup(apiFromFetch(fetch), 'g1')).resolves.toEqual({
      status: 'registered',
      groupId: 'g1'
    });
  });

  test('returns rejected with message on a 409 conflict', async () => {
    const fetch = vi.fn(async () => jsonResponse({ message: 'already exists' }, { status: 409, statusText: 'Conflict' }));
    await expect(registerPermissionGroup(apiFromFetch(fetch), 'g1')).resolves.toEqual({
      status: 'rejected',
      groupId: 'g1',
      message: 'already exists'
    });
  });

  test('returns failed on a server error', async () => {
    const fetch = vi.fn(async () => new Response('', { status: 500, statusText: 'Server Error' }));
    await expect(registerPermissionGroup(apiFromFetch(fetch), 'g1')).resolves.toEqual({
      status: 'failed',
      groupId: 'g1',
      message: 'Permission group could not be registered'
    });
  });
});

describe('deletePermissionGroup', () => {
  test('returns deleted on success', async () => {
    const fetch = vi.fn(async () => jsonResponse({}));
    await expect(deletePermissionGroup(apiFromFetch(fetch), 'g1')).resolves.toEqual({
      status: 'deleted',
      groupId: 'g1'
    });
  });
});

describe('partial group permission updates', () => {
  test('connector removal explicitly disables its connector and capabilities without including unchanged targets', () => {
    expect(permissionSetDifference(
      {
        groupId: 'g1',
        connectorIds: ['gmail', 'slack'],
        capabilities: [
          { connectorId: 'gmail', kind: 'tool', key: 'read' },
          { connectorId: 'slack', kind: 'tool', key: 'read' }
        ]
      },
      {
        groupId: 'g1',
        connectorIds: ['slack'],
        capabilities: [{ connectorId: 'slack', kind: 'tool', key: 'read' }]
      }
    )).toEqual({
      connectors: [{ connector_id: 'gmail', permission_status: 'disabled' }],
      capabilities: [{ connector_id: 'gmail', capability_kind: 'tool', capability_key: 'read', permission_status: 'disabled' }]
    });
  });

  test('update returns saved after sending the changed-only payload', async () => {
    const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({
      status: 'applied',
      group_id: 'g1',
      clients_notified: true
    }));
    const changes = {
      connectors: [],
      capabilities: [{ connector_id: 'c1', capability_kind: 'tool' as const, capability_key: 'op', permission_status: 'enabled' as const }]
    };

    await expect(updateGroupPermissions(apiFromFetch(fetch), 'g1', changes)).resolves.toEqual({ status: 'saved', groupId: 'g1' });
    expect(JSON.parse(String(fetch.mock.calls[0][1]?.body))).toEqual(changes);
  });
});
