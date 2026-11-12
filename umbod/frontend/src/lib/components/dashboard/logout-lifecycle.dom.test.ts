import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { logoutNavigation } from '$lib/admin/infrastructure/logout';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue, sharedConnector } from '$lib/dashboard/test-fixtures';
import { deferred, usageSnapshot } from '$lib/dashboard/usage-fixtures.test-support';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import * as personalConnectionsAdapter from '$lib/personal-connections/infrastructure/personal-connections-api';
import { authorizationHealth, selection } from '$lib/personal-connections/test-fixtures';
import type { WorkspaceProfile } from '$lib/workspace/domain/profile';
import { DashboardIdentityProps } from './identity-props.test-support.svelte';
import ConnectorsPage from './ConnectorsPage.svelte';
import Dashboard from './Dashboard.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function identity(id: string): HeaderAccountIdentityState {
  return { kind: 'visible', name: id, email: null, picture: null, hiddenValues: { id } };
}

function profile(id: string): WorkspaceProfile {
  return { user: { id, name: id, email: null, picture: null }, capabilities: { administration: true } };
}

function refreshBrowserEvents(): void {
  window.dispatchEvent(new Event('focus'));
  document.dispatchEvent(new Event('visibilitychange'));
}

describe('page logout lifetimes', () => {
  test.each([
    { page: 'Dashboard', profilePhase: 'pending' },
    { page: 'Dashboard', profilePhase: 'loaded' },
    { page: 'Connectors', profilePhase: 'pending' },
    { page: 'Connectors', profilePhase: 'loaded' }
  ] as const)('$page disposes protected work during logout with $profilePhase profile', async ({ page, profilePhase }): Promise<void> => {
    const logout = deferred<void>();
    const navigate = vi.spyOn(logoutNavigation, 'logout').mockReturnValue(logout.promise);
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible');
    const pendingProfile = deferred<WorkspaceProfile>();
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValue(pendingProfile.promise);
    if (profilePhase === 'loaded') getProfile.mockResolvedValueOnce(profile('A'));
    const inputs = new DashboardIdentityProps(identity('A'));
    const api = new InMemoryDashboardApi(catalogue);
    const usage = vi.spyOn(api.usage, 'get').mockResolvedValue(usageSnapshot(7, 'account-one', 9));
    const list = vi.spyOn(api.catalogue, 'list');
    const personal = new InMemoryPersonalConnectionsApi([selection], { calendar: authorizationHealth });
    const personalList = vi.spyOn(personal.connections, 'list');
    const health = vi.spyOn(personal.authorization, 'getHealth');
    vi.spyOn(personalConnectionsAdapter, 'browserPersonalConnectionsApi').mockReturnValue(personal);
    const props = {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: (): InMemoryDashboardApi => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    };
    component = page === 'Dashboard'
      ? mount(Dashboard, { target: document.body, props })
      : mount(ConnectorsPage, { target: document.body, props });
    if (page === 'Dashboard') {
      await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('63 calls'));
    } else {
      await vi.waitFor(() => expect(document.body.textContent).toContain(sharedConnector.display_name));
      await vi.waitFor(() => expect(health).toHaveBeenCalledTimes(1));
    }
    if (profilePhase === 'loaded') {
      await vi.waitFor(() => expect(document.querySelector('a[href="/admin/connectors"]')).not.toBeNull());
    }
    const readsBeforeLogout = [usage.mock.calls.length, list.mock.calls.length, personalList.mock.calls.length, health.mock.calls.length];
    const button = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === 'Log out');
    expect(button).toBeDefined();
    button!.click();
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledTimes(1));
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    expect(document.body.textContent).not.toContain(sharedConnector.display_name);
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    refreshBrowserEvents();
    await tick();
    pendingProfile.resolve(profile('B'));
    await tick();
    inputs.replace(identity('B'));
    await tick();
    refreshBrowserEvents();
    await tick();
    expect([usage.mock.calls.length, list.mock.calls.length, personalList.mock.calls.length, health.mock.calls.length]).toEqual(readsBeforeLogout);
    expect(getProfile).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    expect(document.body.textContent).not.toContain(sharedConnector.display_name);
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    expect(button!.disabled).toBe(true);
    logout.resolve();
    await tick();
  });
});
