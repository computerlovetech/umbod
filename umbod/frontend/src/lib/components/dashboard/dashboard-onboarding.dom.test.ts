import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, unmount } from 'svelte';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue } from '$lib/dashboard/test-fixtures';
import { InMemoryPersonalConnectionsApi } from '$lib/personal-connections/infrastructure/in-memory-api';
import { InMemoryWorkspaceApi } from '$lib/workspace/in-memory-api.test-support';
import Dashboard from './Dashboard.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

describe('Dashboard onboarding entry', () => {
  test('links to Getting started without rendering duplicate setup instructions after loading', async (): Promise<void> => {
    component = mount(Dashboard, {
      target: document.body,
      props: {
        createApi: () => new InMemoryDashboardApi({ ...catalogue, personal_enabled: false }),
        createPersonalApi: () => new InMemoryPersonalConnectionsApi([]),
        createWorkspaceApi: () => new InMemoryWorkspaceApi({
          user: { id: 'member', name: 'Member', email: null, picture: null },
          capabilities: { administration: false }
        })
      }
    });
    await vi.waitFor(() => expect(document.querySelector('h1')?.textContent).toBe('Dashboard'));
    expect(document.querySelector('a[href="/getting-started"]')?.textContent?.trim()).toBe('Getting started');
    expect(document.querySelector('[aria-label="MCP setup"]')).toBeNull();
    expect(document.body.textContent).not.toContain('claude mcp add');
    expect(document.body.textContent).not.toContain('codex mcp add');
    expect(document.body.textContent).not.toContain('Generate configuration');
  });
});
