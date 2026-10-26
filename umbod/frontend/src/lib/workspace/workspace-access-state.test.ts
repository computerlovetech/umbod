import { describe, expect, test } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import type { CurrentUserIdentity } from '$lib/header/accountIdentity';
import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue } from '$lib/dashboard/test-fixtures';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { workspaceNavigation } from './navigation';
import { WorkspaceAccessState } from './workspace-access-state.svelte';

const user: CurrentUserIdentity = { id: 'admin', name: 'Alex', email: null };

describe('independent workspace access', () => {
  test('catalogue becomes usable while current user remains pending and navigation stays unprivileged', async (): Promise<void> => {
    let complete!: (identity: CurrentUserIdentity) => void;
    const pending = new Promise<CurrentUserIdentity>((resolve) => { complete = resolve; });
    const access = new WorkspaceAccessState({ currentUser: (): Promise<CurrentUserIdentity> => pending });
    const dashboard = new DashboardState(
      new InMemoryDashboardApi({ ...catalogue, personal_enabled: false }),
      new InMemoryPersonalConnectionsApi([])
    );
    const readingAccess = access.load();
    await dashboard.loadCatalogue();
    expect(dashboard.phase).toBe('ready');
    expect(dashboard.connectors.length).toBeGreaterThan(0);
    expect(access.adminAccess).toBe('checking');
    expect(workspaceNavigation(access.adminAccess === 'allowed').map((item) => item.href)).toEqual(['/dashboard', '/files']);
    complete(user);
    await readingAccess;
    expect(access.accountIdentity).toMatchObject({ kind: 'visible', name: 'Alex' });
    expect(workspaceNavigation(access.adminAccess === 'allowed').map((item) => item.href)).toEqual([
      '/dashboard', '/files', '/admin', '/admin/connectors', '/admin/group-permissions/connectors', '/admin/mcp-setup', '/admin/instance-configuration'
    ]);
    dashboard.dispose();
    access.dispose();
  });

  test.each([403, 500])('failure %s never reveals administration links', async (status): Promise<void> => {
    const access = new WorkspaceAccessState({ currentUser: async (): Promise<CurrentUserIdentity> => { throw new HttpError(status, 'Failed', null); } });
    await access.load();
    expect(access.adminAccess).toBe(status === 403 ? 'denied' : 'unavailable');
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
    expect(workspaceNavigation(access.adminAccess === 'allowed')).toHaveLength(2);
  });

  test('disposed access ignores a late successful response', async (): Promise<void> => {
    let complete!: (identity: CurrentUserIdentity) => void;
    const pending = new Promise<CurrentUserIdentity>((resolve) => { complete = resolve; });
    const access = new WorkspaceAccessState({ currentUser: (): Promise<CurrentUserIdentity> => pending });
    const loading = access.load();
    access.dispose();
    complete(user);
    await loading;
    expect(access.adminAccess).toBe('checking');
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
  });
});
