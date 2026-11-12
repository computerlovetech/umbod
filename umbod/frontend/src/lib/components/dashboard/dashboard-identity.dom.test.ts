import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { WorkspaceProfile } from '$lib/workspace/domain/profile';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue } from '$lib/dashboard/test-fixtures';
import { deferred, usageSnapshot } from '$lib/dashboard/usage-fixtures.test-support';
import type { PersonalUsage } from '$lib/dashboard/domain/usage-schemas';
import { DashboardIdentityProps } from './identity-props.test-support.svelte';
import Dashboard from './Dashboard.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function identity(id: string): HeaderAccountIdentityState {
  return { kind: 'visible', name: `Account ${id}`, email: null, picture: null, hiddenValues: { id: `header-${id}` } };
}

function profile(id: string): WorkspaceProfile {
  return { user: { id: `header-${id}`, name: `Account ${id}`, email: null, picture: null }, capabilities: { administration: true } };
}

const catalogueA = {
  ...catalogue, personal_enabled: false,
};

describe('Dashboard identity source epochs', () => {
  test.each([
    { destination: 'B', pending: false },
    { destination: 'hidden', pending: false },
    { destination: 'B', pending: true },
    { destination: 'hidden', pending: true }
  ] as const)('a parent $destination transition invalidates loaded profile A with pending=$pending data', async ({ destination, pending }): Promise<void> => {
    const inputs = new DashboardIdentityProps(identity('A'));
    const api = new InMemoryDashboardApi(catalogueA);
    const pendingUsageA = deferred<PersonalUsage>();
    const nextUsageB = deferred<PersonalUsage>();
    const profileB = deferred<WorkspaceProfile>();
    const usage = vi.spyOn(api.usage, 'get').mockResolvedValueOnce(usageSnapshot(7, 'account-one', 9));
    if (pending) {
      usage.mockReturnValueOnce(pendingUsageA.promise);
    }
    usage.mockReturnValue(nextUsageB.promise);
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(profile('A')).mockReturnValue(profileB.promise);
    component = mount(Dashboard, { target: document.body, props: {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } });
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('63 calls'));
    expect(document.querySelector('a[href="/admin/connectors"]')).not.toBeNull();
    if (pending) {
      window.dispatchEvent(new Event('focus'));
      await vi.waitFor(() => expect(usage).toHaveBeenCalledTimes(2));
    }
    const readsBeforeTransition = pending ? 2 : 1;
    const usageSignalA = usage.mock.calls[readsBeforeTransition - 1][1];
    inputs.replace(destination === 'B' ? identity('B') : { kind: 'hidden' });
    await tick();
    expect(usageSignalA?.aborted).toBe(true);
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).not.toContain('Account A');
    pendingUsageA.resolve(usageSnapshot(7, 'account-one', 9));
    await tick();
    expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
    if (destination === 'hidden') {
      expect(getProfile).toHaveBeenCalledTimes(1);
      window.dispatchEvent(new Event('focus'));
      const refresh = Array.from(document.querySelectorAll('button')).find((button) => button.textContent?.trim() === 'Refresh usage');
      expect(refresh).toBeDefined();
      refresh!.click();
      await tick();
      expect(usage).toHaveBeenCalledTimes(readsBeforeTransition);
      expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
      return;
    }
    expect(getProfile).toHaveBeenCalledTimes(2);
    expect(usage).toHaveBeenCalledTimes(readsBeforeTransition + 1);
    profileB.resolve(profile('B'));
    nextUsageB.resolve(usageSnapshot(7, 'account-two', 1));
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('7 calls'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
  });

  test.each(['B', 'hidden'] as const)('late prior profile A cannot override a parent %s epoch', async (destination): Promise<void> => {
    const inputs = new DashboardIdentityProps(identity('A'));
    const profileA = deferred<WorkspaceProfile>();
    const profileB = deferred<WorkspaceProfile>();
    const pendingUsageA = deferred<PersonalUsage>();
    const api = new InMemoryDashboardApi(catalogueA);
    const usage = vi.spyOn(api.usage, 'get').mockReturnValueOnce(pendingUsageA.promise).mockResolvedValue(usageSnapshot(7, 'account-two', 1));
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValueOnce(profileA.promise).mockReturnValue(profileB.promise);
    component = mount(Dashboard, { target: document.body, props: {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: () => api,
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } });
    await vi.waitFor(() => expect(getProfile).toHaveBeenCalledTimes(1));
    inputs.replace(destination === 'B' ? identity('B') : { kind: 'hidden' });
    await tick();
    profileA.resolve(profile('A'));
    pendingUsageA.resolve(usageSnapshot(7, 'account-one', 9));
    await tick();
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).not.toContain('Account A');
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    expect(usage).toHaveBeenCalledTimes(destination === 'B' ? 2 : 1);
    if (destination === 'hidden') {
      expect(document.querySelector('[aria-label="Tool activity"]')).toBeNull();
      expect(getProfile).toHaveBeenCalledTimes(1);
      return;
    }
    profileB.resolve(profile('B'));
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')?.textContent).toContain('7 calls'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
  });
});
