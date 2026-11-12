import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { WorkspaceProfile } from '$lib/workspace/domain/profile';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue } from '$lib/dashboard/test-fixtures';
import { deferred } from '$lib/dashboard/usage-fixtures.test-support';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { DashboardIdentityProps } from './identity-props.test-support.svelte';
import ConnectorsPage from './ConnectorsPage.svelte';

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
  connectors: [{ ...catalogue.connectors[0], display_name: 'Account A connector', capabilities: [] }]
};
const catalogueB = {
  ...catalogueA, identity_key: 'account-two',
  connectors: [{ ...catalogueA.connectors[0], display_name: 'Account B connector' }]
};

describe('Connectors identity source epochs', () => {
  test.each([
    { destination: 'B', pending: false },
    { destination: 'hidden', pending: false },
    { destination: 'B', pending: true },
    { destination: 'hidden', pending: true }
  ] as const)('a parent $destination transition invalidates loaded profile A with pending=$pending data', async ({ destination, pending }): Promise<void> => {
    const inputs = new DashboardIdentityProps(identity('A'));
    const api = new InMemoryDashboardApi(catalogueA);
    const pendingCatalogueA = deferred<typeof catalogue>();
    const nextCatalogueB = deferred<typeof catalogue>();
    const profileB = deferred<WorkspaceProfile>();
    const list = vi.spyOn(api.catalogue, 'list').mockResolvedValueOnce(catalogueA);
    if (pending) {
      list.mockReturnValueOnce(pendingCatalogueA.promise);
    }
    list.mockReturnValue(nextCatalogueB.promise);
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValueOnce(profile('A')).mockReturnValue(profileB.promise);
    component = mount(ConnectorsPage, { target: document.body, props: {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: () => api,
      createPersonalApi: () => new InMemoryPersonalConnectionsApi([]),
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } });
    await vi.waitFor(() => expect(document.body.textContent).toContain('Account A connector'));
    expect(document.querySelector('a[href="/admin/connectors"]')).not.toBeNull();
    if (pending) {
      window.dispatchEvent(new Event('focus'));
      await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    }
    const readsBeforeTransition = pending ? 2 : 1;
    const catalogueSignalA = list.mock.calls[readsBeforeTransition - 1][0];
    inputs.replace(destination === 'B' ? identity('B') : { kind: 'hidden' });
    await tick();
    expect(catalogueSignalA?.aborted).toBe(true);
    expect(document.body.textContent).not.toContain('Account A connector');
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).not.toContain('Account A');
    pendingCatalogueA.resolve(catalogueA);
    await tick();
    expect(document.body.textContent).not.toContain('Account A connector');
    if (destination === 'hidden') {
      expect(getProfile).toHaveBeenCalledTimes(1);
      window.dispatchEvent(new Event('focus'));
      await tick();
      expect(list).toHaveBeenCalledTimes(readsBeforeTransition);
      return;
    }
    expect(getProfile).toHaveBeenCalledTimes(2);
    expect(list).toHaveBeenCalledTimes(readsBeforeTransition + 1);
    profileB.resolve(profile('B'));
    nextCatalogueB.resolve(catalogueB);
    await vi.waitFor(() => expect(document.body.textContent).toContain('Account B connector'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
  });

  test.each(['B', 'hidden'] as const)('late prior profile A cannot override a parent %s epoch', async (destination): Promise<void> => {
    const inputs = new DashboardIdentityProps(identity('A'));
    const profileA = deferred<WorkspaceProfile>();
    const profileB = deferred<WorkspaceProfile>();
    const pendingCatalogueA = deferred<typeof catalogue>();
    const api = new InMemoryDashboardApi(catalogueA);
    const list = vi.spyOn(api.catalogue, 'list').mockReturnValueOnce(pendingCatalogueA.promise).mockResolvedValue(catalogueB);
    const getProfile = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValueOnce(profileA.promise).mockReturnValue(profileB.promise);
    component = mount(ConnectorsPage, { target: document.body, props: {
      get accountIdentity(): HeaderAccountIdentityState { return inputs.identity; },
      createApi: () => api,
      createPersonalApi: () => new InMemoryPersonalConnectionsApi([]),
      createWorkspaceApi: () => ({ profile: { get: getProfile } })
    } });
    await vi.waitFor(() => expect(getProfile).toHaveBeenCalledTimes(1));
    inputs.replace(destination === 'B' ? identity('B') : { kind: 'hidden' });
    await tick();
    profileA.resolve(profile('A'));
    pendingCatalogueA.resolve(catalogueA);
    await tick();
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).not.toContain('Account A');
    expect(document.body.textContent).not.toContain('Account A connector');
    expect(document.querySelector('a[href="/admin/connectors"]')).toBeNull();
    expect(list).toHaveBeenCalledTimes(destination === 'B' ? 2 : 1);
    if (destination === 'hidden') {
      expect(getProfile).toHaveBeenCalledTimes(1);
      return;
    }
    profileB.resolve(profile('B'));
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B'));
    await vi.waitFor(() => expect(document.body.textContent).toContain('Account B connector'));
  });

  test.each(['pending', 'loaded'] as const)('resolved profile B fences %s catalogue A without usage requests', async (initialPhase): Promise<void> => {
    const profileB = deferred<WorkspaceProfile>();
    const catalogueReadA = deferred<typeof catalogue>();
    const catalogueReadB = deferred<typeof catalogue>();
    const api = new InMemoryDashboardApi(catalogueA);
    const list = vi.spyOn(api.catalogue, 'list').mockReturnValueOnce(catalogueReadA.promise).mockReturnValue(catalogueReadB.promise);
    const usage = vi.spyOn(api.usage, 'get');
    component = mount(ConnectorsPage, { target: document.body, props: {
      accountIdentity: identity('A'),
      createApi: () => api,
      createPersonalApi: () => new InMemoryPersonalConnectionsApi([]),
      createWorkspaceApi: () => ({ profile: { get: () => profileB.promise } })
    } });
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    const signalA = list.mock.calls[0][0];
    if (initialPhase === 'loaded') {
      catalogueReadA.resolve(catalogueA);
      await vi.waitFor(() => expect(document.body.textContent).toContain('Account A connector'));
    }
    profileB.resolve(profile('B'));
    await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(signalA?.aborted).toBe(true);
    expect(document.body.textContent).not.toContain('Account A connector');
    catalogueReadA.resolve(catalogueA);
    await tick();
    expect(document.body.textContent).not.toContain('Account A connector');
    catalogueReadB.resolve(catalogueB);
    await vi.waitFor(() => expect(document.body.textContent).toContain('Account B connector'));
    expect(document.querySelector('[aria-label="Workspace sidebar"]')?.textContent).toContain('Account B');
    expect(usage).not.toHaveBeenCalled();
  });
});
