import { afterEach, describe, expect, test, vi } from 'vitest';
import { mountWorkspace } from '#lib/components/workspace/mount-workspace.test-support.js';
import { unmount } from 'svelte';
import { dashboardActivityApi } from '#lib/insights/activity/activity.test-support.js';
import { InMemoryWorkspaceApi } from '#lib/workspace/in-memory-api.test-support.js';
import Dashboard from './Dashboard.svelte';

let component: ReturnType<typeof mountWorkspace> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
});

describe('Dashboard onboarding entry', () => {
  test('links to Getting started without rendering duplicate setup instructions after loading', async (): Promise<void> => {
    component = mountWorkspace(Dashboard, {
      target: document.body,
      props: {
        createApi: () => dashboardActivityApi('opaque-member-key', 0),
        createWorkspaceApi: () => new InMemoryWorkspaceApi({
          identity_key: 'opaque-member-key', user: { id: 'member', name: 'Member', email: null, picture: null },
          capabilities: { administration: false }
        })
      }
    }, '/dashboard');
    await vi.waitFor(() => expect(document.querySelector('[aria-label="Tool activity"]')).not.toBeNull());
    expect(document.querySelector('h1')?.textContent).toBe('Dashboard');
    expect(document.querySelector('a[href="/getting-started"]')?.textContent?.trim()).toBe('Getting started');
    expect(document.querySelector('[aria-label="MCP setup"]')).toBeNull();
    expect(document.body.textContent).not.toContain('claude mcp add');
    expect(document.body.textContent).not.toContain('codex mcp add');
    expect(document.body.textContent).not.toContain('Generate configuration');
  });
});
