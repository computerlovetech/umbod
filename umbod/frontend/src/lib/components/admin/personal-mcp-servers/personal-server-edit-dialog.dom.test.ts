import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';
import PersonalServerEditDialog from './PersonalServerEditDialog.svelte';
import type { PolicyProposal } from './policy-form.svelte';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function input(id: string): HTMLInputElement {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLInputElement)) throw new Error(`Input not found: ${id}`);
  return element;
}

function button(label: string): HTMLButtonElement {
  const element = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  if (!element) throw new Error(`Button not found: ${label}`);
  return element;
}

async function fill(id: string, value: string): Promise<void> {
  input(id).value = value;
  input(id).dispatchEvent(new Event('input', { bubbles: true }));
  await tick();
}

function createApi(): InMemoryPersonalServers {
  return new InMemoryPersonalServers([serverFixture()], [{
    ...policyFixture(), requested_scopes: ['records:read'],
    client: { kind: 'preconfigured_public', issuer_url: 'https://issuer.test/Exact/', client_id: 'existing-app' }
  }]);
}

async function openEditor(api: InMemoryPersonalServers, proposal?: PolicyProposal): Promise<{ close: ReturnType<typeof vi.fn> }> {
  const target = document.createElement('div');
  document.body.append(target);
  const close = vi.fn(async (): Promise<void> => {
    if (component) await unmount(component);
    component = undefined;
    target.remove();
  });
  component = mount(PersonalServerEditDialog, {
    target,
    props: {
      connectorId: 'personal', api, proposal, configuration: { get: async () => configurationFixture() },
      close, accessLost: vi.fn(), lockChanged: vi.fn(), reconciliationRequired: vi.fn()
    }
  });
  flushSync();
  await vi.waitFor(() => expect(button('Review changes').disabled).toBe(false));
  await vi.waitFor(() => expect(input('personal-edit-client-id').value).toBe('existing-app'));
  return { close };
}

describe('personal server OAuth editing', (): void => {
  test('loads server identity as read-only and OAuth settings as editable fields', async (): Promise<void> => {
    const api = createApi();
    const get = vi.spyOn(api, 'get');
    const policy = vi.spyOn(api, 'policy');
    await openEditor(api);

    expect(get).toHaveBeenCalledWith('personal');
    expect(policy).toHaveBeenCalledExactlyOnceWith('personal');
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Edit MCP server with personal authorization');
    for (const [id, value] of Object.entries({
      'personal-name': 'Personal server', 'personal-endpoint': 'https://provider.test/mcp',
      'personal-prefix': 'personal', 'personal-description': 'Search records', 'personal-path': 'personal'
    })) {
      expect(input(id).value).toBe(value);
      expect(input(id).readOnly).toBe(true);
      expect(input(id).matches(':disabled')).toBe(false);
    }
    for (const [id, value] of Object.entries({
      'personal-edit-scopes': 'records:read', 'personal-edit-issuer': 'https://issuer.test/Exact/',
      'personal-edit-client-id': 'existing-app'
    })) {
      expect(input(id).value).toBe(value);
      expect(input(id).readOnly).toBe(false);
      expect(input(id).matches(':disabled')).toBe(false);
    }
    expect(document.getElementById('personal-edit-client-kind')?.textContent).toContain('Use an existing client ID');
  });

  test('discovered settings remain suggestions until explicitly accepted and saved', async (): Promise<void> => {
    const api = createApi();
    const replace = vi.spyOn(api, 'replacePolicy');
    await openEditor(api, { issuer: 'https://suggested.test', scopes: ['records:write'] });
    expect(input('personal-edit-issuer').value).toBe('https://issuer.test/Exact/');
    expect(input('personal-edit-scopes').value).toBe('records:read');
    button('Use discovered issuer').click();
    button('Use selected scopes').click();
    await tick();
    expect(input('personal-edit-issuer').value).toBe('https://suggested.test');
    expect(input('personal-edit-scopes').value).toBe('records:write');
    expect(replace).not.toHaveBeenCalled();
    button('Cancel').click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeNull());
    expect((await api.policy('personal')).requested_scopes).toEqual(['records:read']);
  });

  test('cancelling and reopening discards unsaved OAuth changes', async (): Promise<void> => {
    const api = createApi();
    const replace = vi.spyOn(api, 'replacePolicy');
    const { close } = await openEditor(api);
    await fill('personal-edit-scopes', 'records:write');
    await fill('personal-edit-issuer', 'https://draft.test');
    await fill('personal-edit-client-id', 'draft-app');

    button('Cancel').click();
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeNull());
    expect(close).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();

    await openEditor(api);
    expect(input('personal-edit-scopes').value).toBe('records:read');
    expect(input('personal-edit-issuer').value).toBe('https://issuer.test/Exact/');
    expect(input('personal-edit-client-id').value).toBe('existing-app');
    expect((await api.policy('personal')).revision).toBe('r1');
  });

  test('reviews the invalidation warning in the same dialog before revision-checked replacement and closes on success', async (): Promise<void> => {
    const api = createApi();
    const replace = vi.spyOn(api, 'replacePolicy');
    const { close } = await openEditor(api);
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    await fill('personal-edit-scopes', 'records:read records:write');
    await fill('personal-edit-client-id', 'updated-app');

    button('Review changes').click();
    await tick();

    expect(document.querySelectorAll('[role="dialog"]')).toHaveLength(1);
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
    expect(dialog?.textContent).toContain('Save OAuth settings?');
    expect(dialog?.textContent).toContain('Changed settings disconnect all users, cancel pending sign-ins and unpublish the server');
    expect(dialog?.textContent).toContain('Remote tokens are not revoked');
    expect(dialog?.textContent).toContain('Confidential saves rotate the secret');
    expect(replace).not.toHaveBeenCalled();
    expect(close).not.toHaveBeenCalled();

    button('Save settings').click();
    await vi.waitFor(() => expect(close).toHaveBeenCalledOnce());
    await vi.waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeNull());
    expect(replace).toHaveBeenCalledExactlyOnceWith('personal', {
      expected_revision: 'r1',
      settings: {
        requested_scopes: ['records:read', 'records:write'],
        client: { kind: 'preconfigured_public', issuer_url: 'https://issuer.test/Exact/', client_id: 'updated-app' }
      }
    });
    const saved = await api.policy('personal');
    expect(saved.requested_scopes).toEqual(['records:read', 'records:write']);
    expect(saved.revision).not.toBe('r1');
    expect(await api.get('personal')).toEqual(serverFixture());
  });
});
