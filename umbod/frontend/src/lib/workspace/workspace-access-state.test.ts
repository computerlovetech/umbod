import { describe, expect, test, vi } from 'vitest';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import { deferred } from '#lib/dashboard/usage-fixtures.test-support.js';
import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { WorkspaceProfile } from './domain/profile';
import { InMemoryWorkspaceApi } from './in-memory-api.test-support';
import { DashboardState } from '#lib/dashboard/state/dashboard-state.svelte.js';
import { InMemoryDashboardApi } from '#lib/dashboard/infrastructure/in-memory-api.js';
import { catalogue } from '#lib/dashboard/test-fixtures.js';
import { InMemoryPersonalConnectionsApi } from '#lib/personal-connections/infrastructure/in-memory-api.js';
import { workspaceNavigation } from './navigation';
import { resolveWorkspaceAccess } from './admin-access';
import { WorkspaceAccessState } from './workspace-access-state.svelte';
import { WorkspaceScope } from './workspace-scope.svelte';

const user: WorkspaceProfile = { identity_key: 'opaque-admin-key', user: { id: 'admin', name: 'Alex', email: null, picture: null }, capabilities: { administration: true } };

describe('independent workspace access', () => {
  test('personal views hide the previous account until session revalidation finishes', async (): Promise<void> => {
    const next = deferred<WorkspaceProfile>();
    const get = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(user).mockReturnValueOnce(next.promise);
    const access = new WorkspaceAccessState({ profile: { get } });
    const scope = new WorkspaceScope(access);
    await access.load();
    expect(scope.personalIdentity).toMatchObject({ hiddenValues: { id: user.identity_key } });

    scope.suspendPersonal();
    const refresh = scope.refreshPersonal();
    expect(scope.personalChecking).toBe(true);
    expect(scope.personalIdentity).toEqual({ kind: 'hidden' });
    next.resolve({ ...user, identity_key: 'new-account' });
    await refresh;
    expect(scope.personalChecking).toBe(false);
    expect(scope.personalIdentity).toMatchObject({ hiddenValues: { id: 'new-account' } });
  });

  test('workspace logout keeps personal identity hidden when a refresh finishes late', async (): Promise<void> => {
    const next = deferred<WorkspaceProfile>();
    const access = new WorkspaceAccessState({ profile: { get: (): Promise<WorkspaceProfile> => next.promise } });
    const scope = new WorkspaceScope(access);
    const refresh = scope.refreshPersonal();
    scope.dispose();
    next.resolve(user);
    await refresh;
    expect(scope.personalChecking).toBe(false);
    expect(scope.personalIdentity).toEqual({ kind: 'hidden' });
  });

  test('trusted profile keys distinguish equal raw subjects and fence earlier workspace profiles', async (): Promise<void> => {
    const subject = { id: 'same-raw-subject', name: 'Same display name', email: null, picture: null };
    const profileA: WorkspaceProfile = { identity_key: 'opaque-key-7ec4', user: subject, capabilities: { administration: true } };
    const profileB: WorkspaceProfile = { identity_key: 'opaque-key-91bd', user: subject, capabilities: { administration: false } };
    const identityA = (await resolveWorkspaceAccess(new InMemoryWorkspaceApi(profileA))).accountIdentity;
    const identityB = (await resolveWorkspaceAccess(new InMemoryWorkspaceApi(profileB))).accountIdentity;
    expect(profileA.user.id).toBe(profileB.user.id);
    expect(identityA).toMatchObject({ hiddenValues: { id: profileA.identity_key } });
    expect(identityB).toMatchObject({ hiddenValues: { id: profileB.identity_key } });
    let fallback = identityA;
    const pending = deferred<WorkspaceProfile>();
    const get = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValueOnce(pending.promise).mockResolvedValue(profileB);
    const access = new WorkspaceAccessState({ profile: { get } }, () => fallback);
    const loading = access.load();
    fallback = identityB;
    expect(access.observeIdentitySource(identityB)).toBe(true);
    await vi.waitFor(() => expect(access.adminAccess).toBe('denied'));
    pending.resolve(profileA);
    await loading;
    expect(access.effectiveAccountIdentity).toEqual(identityB);
    expect(access.accountIdentity).toEqual(identityB);
    expect(access.adminAccess).toBe('denied');
    access.dispose();
  });

  test('a changed raw source immediately excludes an older profile and revokes administration on observation', async (): Promise<void> => {
    let fallback: HeaderAccountIdentityState = { kind: 'visible', name: 'A', email: null, picture: null, hiddenValues: { id: 'A' } };
    const next = deferred<WorkspaceProfile>();
    const get = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(user).mockReturnValue(next.promise);
    const access = new WorkspaceAccessState({ profile: { get } }, () => fallback);
    await access.load();
    expect(access.effectiveAccountIdentity).toMatchObject({ name: 'Alex' });
    fallback = { kind: 'visible', name: 'B', email: null, picture: null, hiddenValues: { id: 'B' } };
    expect(access.effectiveAccountIdentity).toBe(fallback);
    expect(access.observeIdentitySource(fallback)).toBe(true);
    expect(access.adminAccess).toBe('checking');
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
    fallback = { kind: 'hidden' };
    access.observeIdentitySource(fallback);
    next.resolve(user);
    await Promise.resolve();
    expect(access.effectiveAccountIdentity).toEqual({ kind: 'hidden' });
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
    expect(access.adminAccess).toBe('checking');
    await access.load();
    expect(get).toHaveBeenCalledTimes(2);
    access.dispose();
  });

  test('returning to the same source fingerprint cannot revive a profile from an earlier epoch', async (): Promise<void> => {
    const accountA: HeaderAccountIdentityState = { kind: 'visible', name: 'A', email: null, picture: null, hiddenValues: { id: 'A' } };
    let fallback: HeaderAccountIdentityState = accountA;
    const firstA = deferred<WorkspaceProfile>();
    const pendingB = deferred<WorkspaceProfile>();
    const currentA = deferred<WorkspaceProfile>();
    const get = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValueOnce(firstA.promise)
      .mockReturnValueOnce(pendingB.promise).mockReturnValueOnce(currentA.promise);
    const access = new WorkspaceAccessState({ profile: { get } }, () => fallback);
    const initialRead = access.load();
    fallback = { kind: 'visible', name: 'B', email: null, picture: null, hiddenValues: { id: 'B' } };
    access.observeIdentitySource(fallback);
    fallback = accountA;
    access.observeIdentitySource(fallback);
    currentA.resolve({ ...user, user: { ...user.user, name: 'Current A' }, capabilities: { administration: false } });
    await vi.waitFor(() => expect(access.effectiveAccountIdentity).toMatchObject({ name: 'Current A' }));
    firstA.resolve(user);
    pendingB.resolve(user);
    await initialRead;
    await Promise.resolve();
    expect(access.effectiveAccountIdentity).toMatchObject({ name: 'Current A' });
    expect(access.adminAccess).toBe('denied');
    access.dispose();
  });

  test('catalogue becomes usable while profile remains pending and navigation stays unprivileged', async (): Promise<void> => {
    let complete!: (profile: WorkspaceProfile) => void;
    const pending = new Promise<WorkspaceProfile>((resolve) => { complete = resolve; });
    const access = new WorkspaceAccessState({ profile: { get: (): Promise<WorkspaceProfile> => pending } });
    const dashboard = new DashboardState(
      new InMemoryDashboardApi({ ...catalogue, personal_enabled: false }),
      new InMemoryPersonalConnectionsApi([])
    );
    const readingAccess = access.load();
    await dashboard.loadCatalogue();
    expect(dashboard.phase).toBe('ready');
    expect(dashboard.connectors.length).toBeGreaterThan(0);
    expect(access.adminAccess).toBe('checking');
    expect(workspaceNavigation(access.adminAccess === 'allowed').map((item) => item.href)).toEqual(['/dashboard', '/connectors', '/files', '/insights/agent-behaviour', '/getting-started']);
    complete(user);
    await readingAccess;
    expect(access.accountIdentity).toMatchObject({ kind: 'visible', name: 'Alex' });
    expect(workspaceNavigation(access.adminAccess === 'allowed').map((item) => item.href)).toEqual([
      '/dashboard', '/connectors', '/files', '/insights/agent-behaviour', '/getting-started', '/admin/connectors'
    ]);
    dashboard.dispose();
    access.dispose();
  });

  test.each([403, 500])('failure %s never reveals administration links', async (status): Promise<void> => {
    const access = new WorkspaceAccessState({ profile: { get: async (): Promise<WorkspaceProfile> => { throw new HttpError(status, 'Failed', null); } } });
    await access.load();
    expect(access.adminAccess).toBe(status === 403 ? 'denied' : 'unavailable');
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
    expect(workspaceNavigation(access.adminAccess === 'allowed')).toHaveLength(5);
  });

  test('ordinary profile keeps visible identity without administration navigation', async (): Promise<void> => {
    const access = new WorkspaceAccessState(new InMemoryWorkspaceApi({ ...user, capabilities: { administration: false } }));
    await access.load();
    expect(access.accountIdentity).toMatchObject({ kind: 'visible', name: 'Alex' });
    expect(access.adminAccess).toBe('denied');
    expect(workspaceNavigation(access.adminAccess === 'allowed').map((item) => item.href)).toEqual(['/dashboard', '/connectors', '/files', '/insights/agent-behaviour', '/getting-started']);
    access.dispose();
  });

  test('disposed access ignores a late successful response', async (): Promise<void> => {
    let complete!: (profile: WorkspaceProfile) => void;
    const pending = new Promise<WorkspaceProfile>((resolve) => { complete = resolve; });
    const access = new WorkspaceAccessState({ profile: { get: (): Promise<WorkspaceProfile> => pending } });
    const loading = access.load();
    access.dispose();
    complete(user);
    await loading;
    expect(access.adminAccess).toBe('checking');
    expect(access.accountIdentity).toEqual({ kind: 'hidden' });
  });
});
