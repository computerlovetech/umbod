import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, unmount } from 'svelte';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';
import PersonalServerPolicyPanel from './PersonalServerPolicyPanel.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  window.location.hash = '';
  vi.restoreAllMocks();
});

function mountPanel(): void {
  component = mount(PersonalServerPolicyPanel, {
    target: document.body,
    props: { connectorId: 'personal', api: new InMemoryPersonalServers([serverFixture()], [policyFixture()]), configuration: { get: async () => configurationFixture() } }
  });
}

describe('policy field fragment links', () => {
  test('reveal and focus the Requested scopes field once the policy has loaded', async (): Promise<void> => {
    const scrolled = vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => {});
    window.location.hash = '#personal-policy-personal-scopes';

    mountPanel();

    await vi.waitFor(() => expect(document.activeElement?.id).toBe('personal-policy-personal-scopes'));
    expect(scrolled).toHaveBeenCalledTimes(1);
    expect(scrolled.mock.contexts[0]).toBe(document.getElementById('personal-policy-personal-scopes'));
  });

  test('leave focus alone without a matching fragment', async (): Promise<void> => {
    const scrolled = vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => {});
    window.location.hash = '#elsewhere';

    mountPanel();

    await vi.waitFor(() => expect(document.getElementById('personal-policy-personal-scopes')).not.toBeNull());
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(scrolled).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(document.body);
  });
});
