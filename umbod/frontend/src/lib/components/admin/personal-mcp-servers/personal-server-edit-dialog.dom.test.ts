import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import type { PersonalServerDiscovery } from '#lib/admin/personal-mcp-servers/discovery-administration.js';
import type { EndpointDiscoveryResult } from '#lib/admin/personal-mcp-servers/domain/discovery.js';
import type { PersonalPolicy } from '#lib/admin/personal-mcp-servers/domain/schemas.js';
import { InMemoryPersonalServerDiscovery } from '#lib/admin/personal-mcp-servers/discovery.test-support.js';
import { InMemoryPersonalServers } from '#lib/admin/personal-mcp-servers/in-memory.js';
import { policyFixture, serverFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { configurationFixture } from '#lib/admin/personal-mcp-servers/availability.test-support.js';
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

async function openEditor(api: InMemoryPersonalServers, proposal?: PolicyProposal, discovery: PersonalServerDiscovery = new InMemoryPersonalServerDiscovery([])): Promise<{ close: ReturnType<typeof vi.fn> }> {
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
      connectorId: 'personal', api, proposal, discovery, configuration: { get: async () => configurationFixture() },
      close, accessLost: vi.fn(), lockChanged: vi.fn(), reconciliationRequired: vi.fn()
    }
  });
  flushSync();
  await vi.waitFor(() => expect(button('Review changes').disabled).toBe(false));
  await vi.waitFor(() => expect(input('personal-edit-scopes').value).toBe('records:read'));
  return { close };
}

function dinero(method: 'client_secret_basic' | 'client_secret_post'): Extract<EndpointDiscoveryResult, { kind: 'discovered' }> {
  return { kind: 'discovered', endpoint_url: serverFixture().endpoint_url, issuer_url: 'https://authz.dinero.dk/Exact/', available_scopes: ['records:read', 'records:write'], scope_source: 'resource', automatic_registration: 'available', automatic_client: { kind: 'dynamic_confidential', token_endpoint_auth_method: method }, token_endpoint_auth_methods: ['client_secret_basic', 'client_secret_post'] };
}

async function selectClient(value: 'automatic' | 'preconfigured_public' | 'preconfigured_confidential'): Promise<void> {
  const trigger = document.getElementById('personal-edit-client-kind');
  if (!(trigger instanceof HTMLButtonElement)) throw new Error('Missing client setup selection');
  trigger.click();
  await tick();
  const option = document.querySelector(`[role="option"][data-value="${value}"]`);
  const labels = { automatic: 'Automatic registration', preconfigured_public: 'Use an existing client ID', preconfigured_confidential: 'Use an existing client ID and secret' };
  const item = option ?? Array.from(document.querySelectorAll('[role="option"]')).find((element): boolean => element.textContent?.trim() === labels[value]);
  if (!(item instanceof HTMLElement)) throw new Error('Missing client setup option');
  item.click();
  await tick();
}

function submitReview(): void {
  const form = document.querySelector('form');
  if (!form) throw new Error('Missing policy review form');
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

describe('personal server OAuth editing', (): void => {
  test.each(['client_secret_basic', 'client_secret_post'] as const)('editing automatic confidential policy preserves %s and exact issuer without credential fields', async (method): Promise<void> => {
    const client = { kind: 'dynamic_confidential' as const, approved_issuers: ['https://authz.dinero.dk/Exact/'], token_endpoint_auth_method: method };
    const api = new InMemoryPersonalServers([serverFixture()], [{ ...policyFixture(), requested_scopes: ['records:read'], client }]);
    const replace = vi.spyOn(api, 'replacePolicy');
    const discovery = new InMemoryPersonalServerDiscovery([]);
    const discover = vi.spyOn(discovery, 'discover');
    const { close } = await openEditor(api, undefined, discovery);
    expect(discover).not.toHaveBeenCalled();
    expect(document.getElementById('personal-edit-client-kind')?.textContent).toContain('Automatic registration');
    expect(document.querySelector('input[name="clientId"]')).toBeNull();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.getElementById('personal-edit-issuer')).toBeNull();
    expect(document.getElementById('personal-edit-auth-method')).toBeNull();
    await fill('personal-edit-scopes', 'records:read records:write');
    button('Review changes').click();
    await tick();
    button('Save settings').click();
    await vi.waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(replace).toHaveBeenCalledExactlyOnceWith('personal', { expected_revision: 'r1', settings: { requested_scopes: ['records:read', 'records:write'], client } });
    expect(discover).not.toHaveBeenCalled();
  });
  test.each([
    { kind: 'preconfigured_public', method: 'client_secret_basic' },
    { kind: 'preconfigured_confidential', method: 'client_secret_post' }
  ] as const)('$kind to automatic waits for backend $method and reviews the exact discovered issuer before replacement', async ({ kind, method }): Promise<void> => {
    const client: PersonalPolicy['client'] = kind === 'preconfigured_public'
      ? { kind, issuer_url: 'https://configured.test', client_id: 'old-app' }
      : { kind, issuer_url: 'https://configured.test', client_id: 'old-app', client_secret_configured: true, token_endpoint_auth_method: 'client_secret_basic' };
    const api = new InMemoryPersonalServers([serverFixture()], [{ ...policyFixture(), requested_scopes: ['records:read'], client }]);
    const replace = vi.spyOn(api, 'replacePolicy');
    let resolve!: (result: EndpointDiscoveryResult) => void;
    const pending = new Promise<EndpointDiscoveryResult>((accept): void => { resolve = accept; });
    const discovery: PersonalServerDiscovery = { discover: vi.fn((): Promise<EndpointDiscoveryResult> => pending) };
    const { close } = await openEditor(api, undefined, discovery);
    await selectClient('automatic');
    expect(document.body.textContent).toContain('Discovering automatic application settings');
    expect(button('Review changes').disabled).toBe(true);
    expect(document.querySelector('input[name="clientId"]')).toBeNull();
    expect(document.querySelector('input[type="password"]')).toBeNull();
    submitReview();
    await tick();
    expect(document.body.textContent).not.toContain('Save OAuth settings?');
    expect(replace).not.toHaveBeenCalled();
    resolve(dinero(method));
    await pending;
    await tick();
    expect(discovery.discover).toHaveBeenCalledExactlyOnceWith({ endpoint_url: serverFixture().endpoint_url, issuer_selection: { kind: 'automatic' } });
    expect(document.body.textContent).toContain('Automatic registration issuer:');
    expect(document.body.textContent).toContain(dinero(method).issuer_url);
    expect(document.body.textContent).not.toContain('https://configured.test');
    expect(button('Review changes').disabled).toBe(false);
    await fill('personal-edit-scopes', 'records:read records:write');
    button('Review changes').click();
    await tick();
    expect(replace).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('Save OAuth settings?');
    button('Save settings').click();
    await vi.waitFor(() => expect(close).toHaveBeenCalledOnce());
    expect(replace).toHaveBeenCalledExactlyOnceWith('personal', { expected_revision: 'r1', settings: { requested_scopes: ['records:read', 'records:write'], client: { kind: 'dynamic_confidential', approved_issuers: [dinero(method).issuer_url], token_endpoint_auth_method: method } } });
  });
  test('failed automatic discovery cannot review or save and explicit retry resolves the proposal', async (): Promise<void> => {
    const api = createApi();
    const replace = vi.spyOn(api, 'replacePolicy');
    const discovery = new InMemoryPersonalServerDiscovery([dinero('client_secret_post')]);
    vi.spyOn(discovery, 'discover').mockRejectedValueOnce(new Error('private-provider-failure'));
    await openEditor(api, undefined, discovery);
    await selectClient('automatic');
    expect(document.body.textContent).toContain('Discovery failed');
    expect(document.body.textContent).not.toContain('private-provider-failure');
    expect(button('Review changes').disabled).toBe(true);
    submitReview();
    await tick();
    expect(document.body.textContent).not.toContain('Save OAuth settings?');
    expect(replace).not.toHaveBeenCalled();
    button('Retry discovery').click();
    await tick();
    await tick();
    expect(document.body.textContent).toContain(dinero('client_secret_post').issuer_url);
    expect(button('Review changes').disabled).toBe(false);
  });
  test('unavailable automatic proposal fails closed but permits returning to a manual client', async (): Promise<void> => {
    const api = createApi();
    const metadata = dinero('client_secret_basic');
    const discovery = new InMemoryPersonalServerDiscovery([{ ...metadata, automatic_registration: 'unavailable', automatic_client: { kind: 'unavailable' } }]);
    await openEditor(api, undefined, discovery);
    await selectClient('automatic');
    expect(document.body.textContent).toContain('Automatic setup is unsupported.');
    expect(button('Review changes').disabled).toBe(true);
    submitReview();
    await tick();
    expect(document.body.textContent).not.toContain('Save OAuth settings?');
    await selectClient('preconfigured_public');
    expect(input('personal-edit-client-id').value).toBe('existing-app');
    expect(button('Review changes').disabled).toBe(false);
  });
  test('changing to a manual client while discovery is pending retains manual mode, issuer and credentials', async (): Promise<void> => {
    const api = createApi();
    let resolve!: (result: EndpointDiscoveryResult) => void;
    const pending = new Promise<EndpointDiscoveryResult>((accept): void => { resolve = accept; });
    const discovery: PersonalServerDiscovery = { discover: vi.fn((): Promise<EndpointDiscoveryResult> => pending) };
    await openEditor(api, undefined, discovery);
    await selectClient('automatic');
    await selectClient('preconfigured_confidential');
    await fill('personal-edit-issuer', 'https://manual.test');
    await fill('personal-edit-client-id', 'manual-app');
    await fill('personal-edit-client-secret', 'manual-secret');
    expect(button('Review changes').disabled).toBe(false);
    resolve(dinero('client_secret_post'));
    await pending;
    await tick();
    expect(document.getElementById('personal-edit-client-kind')?.textContent).toContain('Use an existing client ID and secret');
    expect(input('personal-edit-issuer').value).toBe('https://manual.test');
    expect(input('personal-edit-client-id').value).toBe('manual-app');
    expect(input('personal-edit-client-secret').value).toBe('manual-secret');
    expect(button('Review changes').disabled).toBe(false);
  });
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
