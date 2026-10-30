import { beforeEach, describe, expect, test, vi } from 'vitest';
import { load as groupPermissionsLoad } from './+page';
import { load as filesystemLoad } from '../filesystem/+page';
import { load as connectorsLoad } from './connectors/+page';
import { load as layoutLoad } from './+layout';
import { AuthenticationRequiredError, HttpError } from '$lib/admin/infrastructure/transport';

const groups = vi.hoisted(() => ({ list: vi.fn() }));
vi.mock('$lib/admin/infrastructure/admin-api', () => ({ adminApi: (): object => ({ groups }) }));

beforeEach(() => {
  vi.resetAllMocks();
  groups.list.mockResolvedValue([{ group_id: 'team', label: 'Team', description: '', revision: 1 }]);
});

describe('group permissions navigation', () => {
  describe.each([
    { source: '/admin/group-permissions', destination: '/admin/group-permissions/connectors', load: groupPermissionsLoad },
    { source: '/admin/filesystem', destination: '/admin/group-permissions/filesystem', load: filesystemLoad }
  ])('$source redirect', ({ source, destination, load }) => {
    test.each(['', '?connector=billing&operation=list', '?connector=first&connector=second&operation=read&operation=write&extra=1&extra=2', '#access', '?unrelated=%26%3D%23&empty=#group%20permissions'])('retains query and fragment: %s', async (suffix): Promise<void> => {
      await expect(async () => load({ url: new URL('https://umbod.test' + source + suffix) } as never)).rejects.toMatchObject({ status: 307, location: destination + suffix });
      expect(groups.list).not.toHaveBeenCalled();
    });
  });

  test.each([['billing', 'list'], ['team/billing ?#', 'list items+details'], ['a'.repeat(200), 'b'.repeat(200)]])('parses deep links without fetching editor data: %s', async (connectorId, operationId): Promise<void> => {
    const query = new URLSearchParams({ connector: connectorId, operation: operationId });
    const result = await connectorsLoad({ url: new URL('https://umbod.test/admin/group-permissions/connectors?' + query) } as never);
    expect(result).toEqual({ initialTarget: { connectorId, operationId }, originHref: '/admin/openapi-connectors/' + encodeURIComponent(connectorId) });
    expect(groups.list).not.toHaveBeenCalled();
  });

  test.each(['', '?connector=billing', '?operation=list', '?connector=&operation=list', '?connector=billing&operation=', '?connector=%00billing&operation=list', '?connector=billing&operation=list%0Aitems', '?connector=%7F&operation=list', '?connector=' + 'a'.repeat(201) + '&operation=list'])('ignores invalid targets: %s', async (query): Promise<void> => {
    const result = await connectorsLoad({ url: new URL('https://umbod.test/admin/group-permissions/connectors' + query) } as never);
    expect(result).toEqual({ initialTarget: null, originHref: null });
    expect(groups.list).not.toHaveBeenCalled();
  });

  test('loads only the shared catalogue in the persistent parent', async (): Promise<void> => {
    const result = await layoutLoad({ fetch: vi.fn() } as never);
    expect(result).toEqual({ permissionGroups: [{ group_id: 'team', label: 'Team', description: '', revision: 1 }] });
    expect(groups.list).toHaveBeenCalledOnce();
  });

  test.each([401, 403])('preserves rejected access status %s', async (status): Promise<void> => {
    groups.list.mockRejectedValue(new HttpError(status, 'Access denied', null));
    await expect(layoutLoad({ fetch: vi.fn() } as never)).rejects.toMatchObject({ status, body: { message: 'Access denied' } });
  });

  test.each([new AuthenticationRequiredError(), new Error('Unavailable')])('propagates catalogue failures without replay', async (cause): Promise<void> => {
    groups.list.mockRejectedValue(cause);
    await expect(layoutLoad({ fetch: vi.fn() } as never)).rejects.toBe(cause);
    expect(groups.list).toHaveBeenCalledOnce();
  });
});
