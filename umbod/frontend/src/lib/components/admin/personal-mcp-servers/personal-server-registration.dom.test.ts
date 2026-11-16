import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { InMemoryPersonalServerDiscovery } from '$lib/admin/personal-mcp-servers/discovery.test-support';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';
import type { EndpointDiscoveryResult } from '$lib/admin/personal-mcp-servers/domain/discovery';
import PersonalServerRegistration from './PersonalServerRegistration.svelte';
import { PersonalServerFormState } from './personal-server-form-state.svelte';

let component: ReturnType<typeof mount> | undefined;
let state: PersonalServerFormState | undefined;
afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  state?.dispose();
  component = undefined;
  state = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});
function input(id: string): HTMLInputElement {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLInputElement)) throw new Error(`Missing input ${id}`);
  return element;
}
function button(label: string): HTMLButtonElement {
  const element = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  if (!element) throw new Error(`Missing button ${label}`);
  return element;
}
async function fill(id: string, value: string): Promise<void> {
  input(id).value = value;
  input(id).dispatchEvent(new Event('input', { bubbles: true }));
  await tick();
}
function checkbox(label: string): HTMLInputElement {
  const element = Array.from(document.querySelectorAll('label')).find((candidate) => candidate.textContent?.includes(label))?.querySelector('input');
  if (!(element instanceof HTMLInputElement)) throw new Error(`Missing checkbox ${label}`);
  return element;
}
async function check(label: string): Promise<void> {
  const element = checkbox(label);
  element.checked = true;
  element.dispatchEvent(new Event('change', { bubbles: true }));
  await tick();
}
async function open(results: EndpointDiscoveryResult[]): Promise<{ api: InMemoryPersonalServers; discovery: InMemoryPersonalServerDiscovery }> {
  const api = new InMemoryPersonalServers();
  const discovery = new InMemoryPersonalServerDiscovery(results);
  state = new PersonalServerFormState(api, { get: async () => configurationFixture() }, null, discovery);
  await state.reload();
  state.openCreate();
  component = mount(PersonalServerRegistration, { target: document.body, props: { state, close: state.close, reload: state.reload } });
  flushSync();
  return { api, discovery };
}
function result(overrides: Partial<Extract<EndpointDiscoveryResult, { kind: 'discovered' }>> = {}): Extract<EndpointDiscoveryResult, { kind: 'discovered' }> {
  return { kind: 'discovered', endpoint_url: 'https://mcp.test/mcp', issuer_url: 'https://Issuer.test:443/Exact/', available_scopes: ['read', 'write'], scope_source: 'resource', automatic_registration: 'available', token_endpoint_auth_methods: ['none'], ...overrides };
}
function trigger(id: string): HTMLButtonElement {
  const element = document.getElementById(id);
  if (!(element instanceof HTMLButtonElement)) throw new Error(`Missing trigger ${id}`);
  return element;
}
async function key(element: HTMLElement, value: string): Promise<void> {
  element.dispatchEvent(new KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }));
  await tick();
}
async function chooseLast(id: string): Promise<HTMLButtonElement> {
  const element = trigger(id);
  element.focus();
  await key(element, 'Enter');
  await key(element, 'End');
  await key(element, 'Enter');
  return element;
}
async function blurEndpoint(): Promise<void> {
  input('personal-endpoint').dispatchEvent(new FocusEvent('blur'));
  await tick();
  await tick();
}
describe('personal MCP registration interaction', (): void => {
  test('keyboard client-kind and authentication selection preserve original triggers and focus', async (): Promise<void> => {
    await open([]);
    const kind = trigger('personal-registration-client-kind');
    expect(await chooseLast(kind.id)).toBe(kind);
    expect(trigger(kind.id)).toBe(kind);
    expect(kind.value).toBe('preconfigured_confidential');
    expect(document.activeElement).toBe(kind);
    expect(kind.getAttribute('aria-expanded')).toBe('false');
    const method = trigger('personal-registration-auth-method');
    expect(await chooseLast(method.id)).toBe(method);
    expect(trigger(method.id)).toBe(method);
    expect(method.value).toBe('client_secret_post');
    expect(document.activeElement).toBe(method);
    expect(method.getAttribute('aria-expanded')).toBe('false');
  });
  test('discovery completion preserves another focused field node, value and focus', async (): Promise<void> => {
    const { discovery } = await open([]);
    let resolve!: (value: EndpointDiscoveryResult) => void;
    const pending = new Promise<EndpointDiscoveryResult>((accept) => { resolve = accept; });
    vi.spyOn(discovery, 'discover').mockReturnValueOnce(pending);
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    const name = input('personal-name');
    name.focus();
    await fill(name.id, 'Typing during discovery');
    expect(document.body.textContent).toContain('Discovering OAuth settings…');
    resolve(result());
    await pending;
    await tick();
    expect(document.body.textContent).toContain('MCP permissions');
    expect(input(name.id)).toBe(name);
    expect(name.value).toBe('Typing during discovery');
    expect(document.activeElement).toBe(name);
  });
  test('native-invalid confidential creation clears secret before correction and explicit reapproval submits exact settings', async (): Promise<void> => {
    const { api, discovery } = await open([result()]);
    const create = vi.spyOn(api, 'create');
    const replace = vi.spyOn(api, 'replacePolicy');
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    await chooseLast('personal-registration-client-kind');
    await chooseLast('personal-registration-auth-method');
    await fill('personal-name', 'Confidential server');
    await fill('personal-registration-client-id', 'registered-app');
    await fill('personal-registration-client-secret', 'discarded-secret');
    await check('write');
    await fill('personal-custom-scopes', 'custom');
    await check('Approve issuer');
    const description = input('personal-description');
    expect(description.required).toBe(true);
    expect(description.value).toBe('');
    description.dispatchEvent(new Event('invalid', { cancelable: true }));
    await tick();
    expect(input('personal-registration-client-secret').value).toBe('');
    expect(checkbox('Approve issuer').checked).toBe(false);
    expect(create).not.toHaveBeenCalled();
    await fill(description.id, 'Search confidential records');
    await fill('personal-registration-client-secret', 'fresh-secret-sentinel');
    expect(button('Register unpublished server').disabled).toBe(true);
    await check('Approve issuer');
    expect(button('Register unpublished server').disabled).toBe(false);
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create).toHaveBeenCalledWith({
      metadata: { display_name: 'Confidential server', tool_name_prefix: 'Confidential_server', capability_description: 'Search confidential records', public_path: '/mcp/proxies/confidential-server' },
      configuration: { endpoint_url: 'https://mcp.test/mcp', oauth_configuration: { requested_scopes: ['custom', 'write'], client: { kind: 'preconfigured_confidential', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'registered-app', token_endpoint_auth_method: 'client_secret_post', client_secret: 'fresh-secret-sentinel' } } }
    });
    expect(replace).not.toHaveBeenCalled();
    expect(discovery.requests).toEqual([{ endpoint_url: 'https://mcp.test/mcp', issuer_selection: { kind: 'automatic' } }]);
    expect(document.body.innerHTML).not.toContain('fresh-secret-sentinel');
    expect(document.body.innerHTML).not.toContain('discarded-secret');
    expect(state?.form.secret).toBe('');
  });
  test.each([401, 403])('discovery %s clears confidential input, locks creation and fences older success without manual fallback', async (status): Promise<void> => {
    const { api, discovery } = await open([]);
    const create = vi.spyOn(api, 'create');
    let resolve!: (value: EndpointDiscoveryResult) => void;
    const pending = new Promise<EndpointDiscoveryResult>((accept) => { resolve = accept; });
    vi.spyOn(discovery, 'discover').mockReturnValueOnce(pending).mockRejectedValueOnce(new HttpError(status, 'private-auth-diagnostic', null));
    await chooseLast('personal-registration-client-kind');
    await fill('personal-registration-client-secret', 'access-loss-secret');
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    expect(document.body.textContent).toContain('Discovering OAuth settings…');
    await fill('personal-endpoint', 'https://other.test/mcp');
    await blurEndpoint();
    expect(state?.authenticationLost).toBe(true);
    expect(state?.locked).toBe(true);
    expect(state?.creating).toBe(false);
    expect(state?.form.secret).toBe('');
    expect(button('Register unpublished server').disabled).toBe(true);
    expect(document.body.textContent).toContain('Administration access was lost');
    expect(document.body.textContent).not.toContain('Configure manually');
    expect(document.body.textContent).not.toContain('Save without discovered settings');
    expect(document.body.innerHTML).not.toContain('access-loss-secret');
    resolve(result());
    await pending;
    await tick();
    expect(state?.discovery.result).toBeNull();
    expect(state?.discovery.pending).toBe(false);
    expect(document.body.textContent).not.toContain('Approve issuer');
    expect(document.body.textContent).not.toContain('Configure manually');
    expect(document.body.textContent).not.toContain('private-auth-diagnostic');
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await tick();
    expect(create).not.toHaveBeenCalled();
    expect(discovery.discover).toHaveBeenCalledTimes(2);
  });
  test('endpoint first, blur only, unchecked permissions, approval reset and exact unpublished payload', async (): Promise<void> => {
    const { api, discovery } = await open([result()]);
    const create = vi.spyOn(api, 'create');
    expect(document.querySelector('form input')?.id).toBe('personal-endpoint');
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    expect(discovery.requests).toEqual([]);
    await blurEndpoint();
    await blurEndpoint();
    expect(discovery.requests).toHaveLength(1);
    expect(document.body.textContent).toContain('MCP permissions');
    expect(checkbox('read').checked).toBe(false);
    expect(checkbox('write').checked).toBe(false);
    expect(button('Register unpublished server').disabled).toBe(true);
    await check('read');
    await fill('personal-custom-scopes', 'custom');
    await check('Approve issuer');
    expect(button('Register unpublished server').disabled).toBe(false);
    await fill('personal-custom-scopes', 'custom2');
    expect(checkbox('Approve issuer').checked).toBe(false);
    await check('Approve issuer');
    await fill('personal-name', 'Acme');
    await fill('personal-description', 'Search records');
    expect(checkbox('Approve issuer').checked).toBe(true);
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create).toHaveBeenCalledWith({ metadata: { display_name: 'Acme', tool_name_prefix: 'Acme', capability_description: 'Search records', public_path: '/mcp/proxies/acme' }, configuration: { endpoint_url: 'https://mcp.test/mcp', oauth_configuration: { requested_scopes: ['custom2', 'read'], client: { kind: 'dynamic_public', approved_issuers: ['https://Issuer.test:443/Exact/'] } } } });
    expect(discovery.requests).toHaveLength(1);
  });
  test.each([
    { source: 'resource' as const, label: 'No scopes advertised' },
    { source: 'unavailable' as const, label: 'Scopes unavailable' }
  ])('renders $label distinctly with custom scopes available', async ({ source, label }): Promise<void> => {
    await open([result({ available_scopes: [], scope_source: source })]);
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    expect(document.body.textContent).toContain(label);
    expect(input('personal-custom-scopes')).toBeTruthy();
    expect(checkbox('Approve issuer').parentElement?.textContent).toContain('No explicit scopes');
  });
  test('pending discovery permits unrelated typing but cannot submit and close fences the result', async (): Promise<void> => {
    const { api, discovery } = await open([]);
    let resolve!: (value: EndpointDiscoveryResult) => void;
    const pending = new Promise<EndpointDiscoveryResult>((accept) => { resolve = accept; });
    vi.spyOn(discovery, 'discover').mockReturnValueOnce(pending);
    const create = vi.spyOn(api, 'create');
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    expect(document.body.textContent).toContain('Discovering OAuth settings…');
    await fill('personal-name', 'Still editable');
    expect(input('personal-name').value).toBe('Still editable');
    expect(input('personal-name').matches(':disabled')).toBe(false);
    expect(button('Register unpublished server').disabled).toBe(true);
    document.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await tick();
    expect(create).not.toHaveBeenCalled();
    button('Cancel').click();
    await tick();
    resolve(result());
    await pending;
    await tick();
    expect(state?.discovery.result).toBeNull();
    expect(state?.discovery.pending).toBe(false);
  });
  test('failed metadata requires both manual action and acknowledgement', async (): Promise<void> => {
    const { discovery } = await open([]);
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    expect(document.body.textContent).toContain('Discovery failed');
    expect(document.querySelector('input[name="scopes"]')).toBeNull();
    button('Configure manually').click();
    await tick();
    expect(input('personal-manual-scopes')).toBeTruthy();
    expect(button('Register unpublished server').disabled).toBe(true);
    await check('Save without discovered settings');
    expect(button('Register unpublished server').disabled).toBe(false);
    button('Retry discovery').click();
    await tick();
    expect(discovery.requests).toHaveLength(2);
    expect(button('Register unpublished server').disabled).toBe(true);
  });
  test('unsupported registration stays automatic until explicit existing-client selection', async (): Promise<void> => {
    await open([result({ automatic_registration: 'unavailable' })]);
    await fill('personal-endpoint', 'https://mcp.test/mcp');
    await blurEndpoint();
    expect(document.body.textContent).toContain('Automatic registration unavailable');
    await check('Approve issuer');
    expect(button('Register unpublished server').disabled).toBe(true);
    button('Automatic registration⌄').click();
    await tick();
    const option = Array.from(document.querySelectorAll('[role="option"]')).find((element) => element.textContent?.includes('Use an existing client ID'));
    if (!(option instanceof HTMLElement)) throw new Error('Missing existing-client option');
    option.click();
    await tick();
    expect(input('personal-registration-issuer').readOnly).toBe(true);
    expect(input('personal-registration-issuer').value).toBe(result().issuer_url);
    expect(input('personal-registration-client-id').required).toBe(true);
    expect(checkbox('Approve issuer').checked).toBe(false);
  });
});
