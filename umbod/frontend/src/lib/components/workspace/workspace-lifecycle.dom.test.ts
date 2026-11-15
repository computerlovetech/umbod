import { afterEach, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { workspaceApi } from '$lib/workspace/infrastructure/workspace-api';
import { deferred } from '$lib/dashboard/usage-fixtures.test-support';
import type { WorkspaceProfile } from '$lib/workspace/domain/profile';
import { WorkspaceRoute } from './workspace-route.test-support.svelte';
import WorkspaceRootHarness from './WorkspaceRootHarness.test-support.svelte';

const navigation = vi.hoisted(() => ({
  route: undefined as WorkspaceRoute | undefined,
  after: undefined as (() => void) | undefined
}));

vi.mock('$app/state', () => ({
  page: {
    get url(): URL { return new URL(navigation.route?.pathname ?? '/dashboard', 'https://umbod.test'); },
    error: null, status: 200, route: { id: '/(workspace)/dashboard' }
  },
  navigating: { to: null, from: null }
}));
vi.mock('$app/navigation', () => ({
  beforeNavigate: vi.fn(),
  afterNavigate: (callback: () => void): void => { navigation.after = callback; }
}));
vi.mock('$lib/workspace/infrastructure/workspace-api', () => ({ workspaceApi: vi.fn() }));
vi.mock('$lib/identity-directory/api', () => ({
  identityDirectoryApi: () => ({ observations: { observe: async (): Promise<void> => {} } })
}));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  navigation.route = undefined;
  navigation.after = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

const profile: WorkspaceProfile = {
  identity_key: 'account-one',
  user: { id: 'member', name: 'Member', email: 'member@example.test', picture: null },
  capabilities: { administration: false }
};

test('root retains sidebar and account DOM across child routes and reloads only after leaving the workspace group', async (): Promise<void> => {
  const get = vi.fn<() => Promise<WorkspaceProfile>>().mockResolvedValue(profile);
  vi.mocked(workspaceApi).mockReturnValue({ profile: { get } });
  const route = new WorkspaceRoute();
  navigation.route = route;
  component = mount(WorkspaceRootHarness, { target: document.body, props: { route } });
  await vi.waitFor(() => expect(document.querySelector('.account-name')?.textContent).toBe('Member'));
  const sidebar = document.querySelector('[aria-label="Workspace sidebar"]');
  const account = document.querySelector('.account-details');
  const logout = document.querySelector('.logout-action button');
  expect(sidebar).not.toBeNull();
  expect(account).not.toBeNull();
  expect(logout).not.toBeNull();
  let heading = document.querySelector('h1');

  for (const path of ['/connectors', '/files', '/getting-started', '/getting-started/telemetry', '/dashboard']) {
    route.navigate(path);
    await tick();
    navigation.after!();
    expect(document.querySelector('h1')?.textContent).toBe(path);
    expect(document.querySelector('h1')).not.toBe(heading);
    heading = document.querySelector('h1');
    expect(document.querySelector('[aria-label="Workspace sidebar"]')).toBe(sidebar);
    expect(document.querySelector('.account-details')).toBe(account);
    expect(document.querySelector('.logout-action button')).toBe(logout);
    expect(document.querySelector('nav a[aria-current="page"]')?.getAttribute('href')).toBe(path.startsWith('/getting-started') ? '/getting-started' : path);
    expect(get).toHaveBeenCalledTimes(1);
  }

  route.navigate('/outside');
  await tick();
  expect(document.querySelector('[aria-label="Workspace sidebar"]')).toBeNull();
  route.navigate('/files');
  await tick();
  await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  expect(document.querySelector('[aria-label="Workspace sidebar"]')).not.toBe(sidebar);
});

test('leaving the group fences a late profile without caching it for reentry', async (): Promise<void> => {
  const pending = deferred<WorkspaceProfile>();
  const get = vi.fn<() => Promise<WorkspaceProfile>>().mockReturnValueOnce(pending.promise).mockResolvedValue({ ...profile, user: { ...profile.user, name: 'Replacement' } });
  vi.mocked(workspaceApi).mockReturnValue({ profile: { get } });
  const route = new WorkspaceRoute();
  navigation.route = route;
  component = mount(WorkspaceRootHarness, { target: document.body, props: { route } });
  await vi.waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  route.navigate('/outside');
  await tick();
  pending.resolve(profile);
  await tick();
  expect(document.querySelector('[aria-label="Workspace sidebar"]')).toBeNull();
  route.navigate('/files');
  await tick();
  await vi.waitFor(() => expect(document.querySelector('.account-name')?.textContent).toBe('Replacement'));
  expect(get).toHaveBeenCalledTimes(2);
  expect(document.body.textContent).not.toContain('Member');
});
