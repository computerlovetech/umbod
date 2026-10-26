import { beforeEach, describe, expect, test, vi } from 'vitest';
import { load as groupPermissionsLoad } from './+page';
import { load as filesystemLoad } from '../filesystem/+page';
import { load as connectorsLoad } from './connectors/+page';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';
import { exactMatchGuidance } from '$lib/admin/group-permissions';

const permissions = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), listAssignableTargets: vi.fn() }));
vi.mock('$lib/admin/infrastructure/admin-api', () => ({ adminApi: () => ({ groupPermissions: { permissions } }) }));

beforeEach(() => {
  vi.resetAllMocks();
  permissions.list.mockResolvedValue([{ groupId: 'team' }]);
  permissions.get.mockResolvedValue({ groupId: 'team', connectorIds: ['billing'], capabilities: [] });
  permissions.listAssignableTargets.mockResolvedValue([{ id: 'billing', displayName: 'Billing', description: '', capabilities: [] }]);
});

describe('group permissions navigation', () => {
  describe.each([
    { source: '/admin/group-permissions', destination: '/admin/group-permissions/connectors', load: groupPermissionsLoad },
    { source: '/admin/filesystem', destination: '/admin/group-permissions/filesystem', load: filesystemLoad }
  ])('$source redirect', ({ source, destination, load }) => {
    test.each([
      '',
      '?connector=billing&operation=list',
      '?connector=team%2Fbilling&operation=list%20items&unrelated=a%2Bb',
      '?connector=first&connector=second&operation=read&operation=write&extra=1&extra=2',
      '#access',
      '?unrelated=%26%3D%23&empty=#group%20permissions'
    ])('retains the complete query and fragment: %s', async (suffix): Promise<void> => {
      await expect(async () => load({ url: new URL(`https://umbod.test${source}${suffix}`) } as never)).rejects.toMatchObject({ status: 307, location: `${destination}${suffix}` });
      expect(permissions.list).not.toHaveBeenCalled();
    });
  });

  test.each([
    ['billing', 'list'],
    ['team/billing ?#', 'list items+details'],
    ['a'.repeat(200), 'b'.repeat(200)]
  ])('loads a connector deep link for %s', async (connectorId, operationId): Promise<void> => {
    const query = new URLSearchParams({ connector: connectorId, operation: operationId, unrelated: 'preserved' });
    const result = await connectorsLoad({ url: new URL(`https://umbod.test/admin/group-permissions/connectors?${query}#details`), fetch: vi.fn() } as never);
    expect(result).toMatchObject({
      status: 'ready', groups: [{ groupId: 'team' }],
      preloadedGroup: { groupId: 'team', connectorIds: ['billing'], capabilities: [] },
      assignableTargets: [{ id: 'billing' }], exactMatchGuidance,
      initialTarget: { connectorId, operationId }, originHref: `/admin/openapi-connectors/${encodeURIComponent(connectorId)}`
    });
    expect(permissions.list).toHaveBeenCalledOnce();
    expect(permissions.get).toHaveBeenCalledWith('team');
    expect(permissions.listAssignableTargets).toHaveBeenCalledOnce();
  });

  test.each([
    '', '?connector=billing', '?operation=list', '?connector=&operation=list', '?connector=billing&operation=',
    '?connector=%00billing&operation=list', '?connector=billing&operation=list%0Aitems',
    '?connector=%7F&operation=list', `?connector=${'a'.repeat(201)}&operation=list`,
    `?connector=billing&operation=${'b'.repeat(201)}`
  ])('ignores invalid or incomplete deep links: %s', async (query): Promise<void> => {
    const result = await connectorsLoad({ url: new URL(`https://umbod.test/admin/group-permissions/connectors${query}`), fetch: vi.fn() } as never);
    expect(result).toMatchObject({ status: 'ready', groups: [{ groupId: 'team' }], initialTarget: null, originHref: null });
    expect(permissions.get).toHaveBeenCalledWith('team');
  });

  test('loads the empty workspace without selected-group requests', async (): Promise<void> => {
    permissions.list.mockResolvedValue([]);
    const result = await connectorsLoad({ url: new URL('https://umbod.test/admin/group-permissions/connectors'), fetch: vi.fn() } as never);
    expect(result).toEqual({ status: 'ready', groups: [], preloadedGroup: null, assignableTargets: [], exactMatchGuidance, initialTarget: null, originHref: null });
    expect(permissions.get).not.toHaveBeenCalled();
    expect(permissions.listAssignableTargets).not.toHaveBeenCalled();
  });

  test.each([401, 403])('preserves rejected access status %s', async (status): Promise<void> => {
    permissions.list.mockRejectedValue(new HttpError(status, 'Access denied', null));
    await expect(connectorsLoad({ url: new URL('https://umbod.test/admin/group-permissions/connectors?connector=billing&operation=list'), fetch: vi.fn() } as never)).rejects.toMatchObject({ status, body: { message: 'Access denied' } });
    expect(permissions.list).toHaveBeenCalledOnce();
    expect(permissions.get).not.toHaveBeenCalled();
  });

  test.each([new AuthenticationRequiredError(), new Error('Unavailable')])('propagates loader failures without replay', async (cause): Promise<void> => {
    permissions.list.mockRejectedValue(cause);
    await expect(connectorsLoad({ url: new URL('https://umbod.test/admin/group-permissions/connectors'), fetch: vi.fn() } as never)).rejects.toBe(cause);
    expect(permissions.list).toHaveBeenCalledOnce();
  });
});
