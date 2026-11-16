import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import * as adminApiModule from '$lib/admin/infrastructure/admin-api';
import { InMemoryPersonalOAuthSetup } from '$lib/admin/personal-mcp-servers/setup.test-support';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { DownstreamMcpConnectorsRoute } from '$lib/admin/downstream-mcp-connectors-api';
import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceBundle } from './downstream-mcp-workspace-state.svelte';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/admin/downstream-mcp-connectors?capability=tools') } }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), invalidateAll: vi.fn() }));
vi.mock('$lib/components/feedback', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));

function grafanaBundle(published: boolean): DownstreamMcpWorkspaceBundle {
  return {
    mode: 'shared',
    connector: {
      connector_id: 'grafana', display_name: 'Grafana', tool_name_prefix: 'grafana', icon_url: '',
      capability_description: 'Grafana tools', base_capability_description: 'Grafana tools', effective_capability_description: 'Grafana tools',
      capability_description_override: { state: 'system', revision: 0 },
      endpoint_url: 'https://grafana.test/mcp', public_path: '/mcp/proxies/grafana', public_url: 'https://umbod.test/mcp/proxies/grafana',
      auth_mode: 'none', authorization_mode: 'shared', header_type: 'bearer', custom_header_name: null, credential_configured: false,
      publication_status: published ? 'published' : 'unpublished', health: { status: 'healthy', checked_at: '2026-01-01T00:00:00Z', reason: null }
    },
    catalog: {
      discovered_at: '2026-01-01T00:00:00Z',
      tools: [{ name: 'search_dashboards', title: 'Search dashboards', description: 'Find dashboards', input_schema: {}, output_schema: null, activation_status: 'enabled' }]
    },
    promptCatalog: { prompts: [], available_actions: [] },
    resourceCatalog: { resources: [], availableActions: [] }
  };
}

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const result = Array.from(scope.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label || candidate.getAttribute('aria-label') === label);
  if (!result) throw new Error(`Button not found: ${label}`);
  return result;
}

type MutationApi = Pick<DownstreamMcpConnectorsRoute, 'publish' | 'unpublish' | 'delete' | 'list'>;

function mutationApi(bundle: DownstreamMcpWorkspaceBundle): { [Key in keyof MutationApi]: ReturnType<typeof vi.fn<MutationApi[Key]>> } {
  return {
    publish: vi.fn<MutationApi['publish']>().mockResolvedValue({ ...bundle.connector, publication_status: 'published' }),
    unpublish: vi.fn<MutationApi['unpublish']>().mockResolvedValue({ ...bundle.connector, publication_status: 'unpublished' }),
    delete: vi.fn<MutationApi['delete']>().mockResolvedValue(undefined),
    list: vi.fn<MutationApi['list']>().mockResolvedValue({ connectors: [bundle.connector] })
  };
}

let component: ReturnType<typeof mount> | undefined;
let ownedOperations: DownstreamMcpMutationState | undefined;

afterEach(async (): Promise<void> => {
  ownedOperations?.dispose();
  ownedOperations = undefined;
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

function renderWorkspace(published: boolean): { api: ReturnType<typeof mutationApi>; navigate: ReturnType<typeof vi.fn> } {
  const bundle = grafanaBundle(published);
  const api = mutationApi(bundle);
  const navigate = vi.fn();
  const operations = new DownstreamMcpMutationState(api, navigate);
  ownedOperations = operations;
  const state = new DownstreamMcpWorkspaceState(undefined, undefined, bundle, undefined, undefined, undefined, undefined, undefined, operations);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(DownstreamMcpWorkspace, {
    target,
    props: { connectors: [bundle.connector], selected: bundle.connector, catalog: bundle.catalog, state }
  });
  flushSync();
  return { api, navigate };
}

async function openConfirmation(label: string): Promise<HTMLElement> {
  button('Open actions for Grafana').click();
  await tick();
  button(label, document.querySelector('[role="menu"]')!).click();
  await tick();
  const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
  expect(dialog?.textContent).toContain(`${label} Grafana?`);
  if (!dialog) throw new Error('Publication confirmation is missing');
  return dialog;
}

async function renderPersonalWorkspace(validated: boolean = true): Promise<{
  composite: adminApiModule.AdminApi;
  state: DownstreamMcpWorkspaceState;
  operations: DownstreamMcpMutationState;
  api: ReturnType<typeof mutationApi>;
  navigate: ReturnType<typeof vi.fn>;
}> {
  const connector = serverFixture();
  const personalApi = new InMemoryPersonalServers([connector], [policyFixture()]);
  const composite = new adminApiModule.AdminApi({ request: vi.fn().mockRejectedValue(new Error('Unexpected transport request')) });
  vi.spyOn(composite.personalServers, 'get').mockImplementation((id) => personalApi.get(id));
  vi.spyOn(composite.personalServers, 'policy').mockImplementation((id) => personalApi.policy(id));
  vi.spyOn(composite.personalServers, 'replacePolicy').mockImplementation((id, input) => personalApi.replacePolicy(id, input));
  const setup = new InMemoryPersonalOAuthSetup();
  if (validated) setup.current = setup.validation;
  vi.spyOn(composite.personalOAuthSetup, 'status').mockImplementation((id) => setup.status(id));
  vi.spyOn(adminApiModule, 'adminApi').mockReturnValue(composite);
  const bundle: DownstreamMcpWorkspaceBundle = { mode: 'personal', connector };
  const api = mutationApi(bundle);
  const navigate = vi.fn();
  const operations = new DownstreamMcpMutationState(api, navigate);
  ownedOperations = operations;
  const state = new DownstreamMcpWorkspaceState(undefined, undefined, bundle, undefined, undefined, undefined, undefined, undefined, operations);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(DownstreamMcpWorkspace, {
    target, props: { connectors: [connector], selected: connector, state }
  });
  flushSync();
  await vi.waitFor(() => expect(state.personalSetup.pending).toBeNull());
  return { composite, state, operations, api, navigate };
}

async function beginPolicyReplacement(): Promise<HTMLDialogElement> {
  button('Open actions for Personal server').click();
  await tick();
  button('Edit', document.querySelector('[role="menu"]')!).click();
  await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('#personal-name')?.value).toBe('Personal server'));
  const scopes = document.querySelector<HTMLInputElement>('#personal-edit-scopes');
  if (!scopes) throw new Error('Requested scopes input is missing');
  scopes.value = 'records:read';
  scopes.dispatchEvent(new Event('input', { bubbles: true }));
  await tick();
  button('Review changes').click();
  await tick();
  button('Save settings').click();
  await tick();
  const dialog = document.querySelector('dialog');
  if (!dialog) throw new Error('Personal server editor is missing');
  return dialog;
}

describe('personal MCP editing from the action menu', (): void => {
  test('unvalidated personal servers have no publication action', async (): Promise<void> => {
    const { api } = await renderPersonalWorkspace(false);
    button('Open actions for Personal server').click();
    await tick();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(menu?.textContent).not.toContain('Publish');
    expect(button('Edit', menu!).disabled).toBe(false);
    expect(api.publish).not.toHaveBeenCalled();
  });

  test('validated personal publication reconciles in place without testing sign-in', async (): Promise<void> => {
    const { api, navigate } = await renderPersonalWorkspace();
    const workspace = document.querySelector('[aria-label="MCP connectors workspace"]');
    const panel = document.querySelector('[aria-label="Personal OAuth setup"]');
    button('Open actions for Personal server').click();
    await tick();
    button('Publish', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) throw new Error('Publication confirmation is missing');
    button('Publish', dialog).click();
    await vi.waitFor(() => expect(api.publish).toHaveBeenCalledExactlyOnceWith('personal'));
    await vi.waitFor(() => expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('published'));
    expect(document.querySelector('[aria-label="MCP connectors workspace"]')).toBe(workspace);
    expect(document.querySelector('[aria-label="Personal OAuth setup"]')).toBe(panel);
    expect(document.body.textContent).toContain('Sign-in not tested');
    expect(navigate).not.toHaveBeenCalled();
  });
  test('keeps a pending policy replacement mounted and locked through window Escape and native cancel', async (): Promise<void> => {
    const { composite, operations, state, api } = await renderPersonalWorkspace();
    type Policy = Awaited<ReturnType<typeof composite.personalServers.replacePolicy>>;
    let complete!: (policy: Policy) => void;
    vi.mocked(composite.personalServers.replacePolicy).mockImplementation(() => new Promise<Policy>((resolve) => { complete = resolve; }));
    const dialog = await beginPolicyReplacement();

    expect(composite.personalServers.replacePolicy).toHaveBeenCalledOnce();
    expect(operations.locked).toBe(true);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await tick();
    expect(document.querySelector('dialog')).toBe(dialog);
    expect(state.modal).toBe('personal-edit');
    expect(operations.formLocked).toBe(true);

    const cancel = new Event('cancel', { cancelable: true });
    dialog.dispatchEvent(cancel);
    await tick();
    expect(cancel.defaultPrevented).toBe(true);
    expect(document.querySelectorAll('dialog')).toHaveLength(1);
    expect(document.querySelector('dialog')).toBe(dialog);
    expect(dialog.open).toBe(true);
    expect(operations.locked).toBe(true);
    button('Open actions for Personal server').click();
    await tick();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    for (const label of ['Edit', 'Publish', 'Delete']) expect(button(label, menu!).disabled).toBe(true);
    expect(composite.personalServers.replacePolicy).toHaveBeenCalledOnce();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();

    complete({ ...policyFixture(), revision: 'r2', requested_scopes: ['records:read'] });
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(state.modal).toBeNull();
    expect(operations.locked).toBe(false);
    expect(composite.personalServers.replacePolicy).toHaveBeenCalledOnce();
  });

  test('retains unknown-outcome blocking after closing the editor and offers reload without retrying', async (): Promise<void> => {
    const { composite, operations, api, navigate } = await renderPersonalWorkspace();
    let reject!: (error: Error) => void;
    vi.mocked(composite.personalServers.replacePolicy).mockImplementation(() => new Promise((_resolve, rejectReplacement) => { reject = rejectReplacement; }));
    const dialog = await beginPolicyReplacement();

    reject(new NetworkError(new Error('private replacement diagnostic')));
    await vi.waitFor(() => expect(dialog.querySelector('[role="alert"]')?.textContent).toContain('The outcome is unknown'));
    const message = dialog.querySelector('[role="alert"]')!.textContent!;
    expect(operations.locked).toBe(true);
    button('Open actions for Personal server').click();
    await tick();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    for (const label of ['Publish', 'Delete']) expect(button(label, menu!).disabled).toBe(true);

    button('Close', dialog).click();
    await tick();

    expect(document.querySelector('dialog')).toBeNull();
    expect(operations.formLocked).toBe(false);
    expect(operations.blocked).toBe(true);
    expect(operations.locked).toBe(true);
    expect(operations.message).toBe(message);
    expect(document.querySelector('[role="alert"]')?.textContent).toContain(message);
    expect(document.body.textContent).not.toContain('private replacement diagnostic');
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(button('Reload servers').disabled).toBe(false);
    for (const action of ['publish', 'delete'] as const) {
      operations.request(action, 'personal', 'Personal server');
      expect(operations.pending).toBeNull();
    }
    expect(composite.personalServers.replacePolicy).toHaveBeenCalledOnce();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();

    button('Reload servers').click();
    await tick();
    expect(navigate).toHaveBeenCalledExactlyOnceWith();
    expect(composite.personalServers.replacePolicy).toHaveBeenCalledOnce();
    expect(operations.blocked).toBe(true);
  });

  test('opens the selected personal server editor and dismisses it without changing the server', async (): Promise<void> => {
    const { composite, state } = await renderPersonalWorkspace();
    const { get, policy, replacePolicy: replace } = composite.personalServers;
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    vi.mocked(get).mockClear();
    vi.mocked(policy).mockClear();
    button('Open actions for Personal server').click();
    await tick();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(menu?.textContent).not.toContain('Configure');
    expect(button('Edit', menu!).disabled).toBe(false);
    button('Edit', menu!).click();
    await tick();

    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('#personal-name')?.value).toBe('Personal server'));
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('Edit MCP server with personal authorization');
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(get).toHaveBeenCalledExactlyOnceWith('personal');
    expect(policy).toHaveBeenCalledExactlyOnceWith('personal');

    button('Cancel', document.querySelector('[role="dialog"]')!).click();
    await tick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(state.modal).toBeNull();
    expect(replace).not.toHaveBeenCalled();
    expect(document.querySelector('article')?.textContent).toContain('Personal server');
  });
});

describe('shared MCP publication from the action menu', (): void => {
  test.each([
    { label: 'Publish', published: false, action: 'publish', otherAction: 'unpublish', status: 'published' },
    { label: 'Unpublish', published: true, action: 'unpublish', otherAction: 'publish', status: 'unpublished' }
  ] as const)('dispatches $label exactly once after confirmation for a healthy discovered connector', async ({ label, published, action, otherAction, status }): Promise<void> => {
    const { api, navigate } = renderWorkspace(published);
    const workspace = document.querySelector('[aria-label="MCP connectors workspace"]');
    const detail = document.querySelector('article');
    const search = document.querySelector<HTMLInputElement>('input[type="search"]')!;
    search.value = 'dashboards';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    const dialog = await openConfirmation(label);
    expect(api[action]).not.toHaveBeenCalled();
    expect(api.list).not.toHaveBeenCalled();
    expect(document.querySelector('[role="menu"]')).toBeNull();

    const confirm = button(label, dialog);
    confirm.click();
    confirm.click();
    await tick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    await vi.waitFor(() => expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain(`healthy · ${status}`));
    expect(document.querySelector('[aria-label="MCP connectors workspace"]')).toBe(workspace);
    expect(document.querySelector('article')).toBe(detail);
    expect(document.querySelector('input[type="search"]')).toBe(search);
    expect(search.value).toBe('dashboards');
    expect(detail?.textContent).toContain(status === 'published' ? 'Published' : 'Unpublished');
    expect(navigate).not.toHaveBeenCalled();
    expect(api[action]).toHaveBeenCalledExactlyOnceWith('grafana');
    expect(api[otherAction]).not.toHaveBeenCalled();
    expect(api.list).not.toHaveBeenCalled();
    button('Open actions for Grafana').click();
    await tick();
    expect(button(label === 'Publish' ? 'Unpublish' : 'Publish', document.querySelector('[role="menu"]')!).disabled).toBe(false);
  });

  test('cancelling publication never dispatches an operation', async (): Promise<void> => {
    const { api, navigate } = renderWorkspace(false);
    const dialog = await openConfirmation('Publish');

    button('Cancel', dialog).click();
    await tick();

    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  test('shows pending feedback and blocks competing mutations until publication completes', async (): Promise<void> => {
    const { api, navigate } = renderWorkspace(false);
    let complete!: (value: Awaited<ReturnType<MutationApi['publish']>>) => void;
    api.publish.mockImplementation(() => new Promise((resolve) => { complete = resolve; }));
    const dialog = await openConfirmation('Publish');

    button('Publish', dialog).click();
    await tick();

    expect(document.querySelector('[role="status"]')?.textContent).toContain('Updating MCP connector');
    expect(api.list).not.toHaveBeenCalled();
    button('Open actions for Grafana').click();
    await tick();
    const menu = document.querySelector('[role="menu"]')!;
    for (const label of ['Publish', 'Configure', 'Refresh discovery', 'Delete']) {
      expect(button(label, menu).disabled).toBe(true);
      button(label, menu).click();
    }
    await tick();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(api.publish).toHaveBeenCalledExactlyOnceWith('grafana');
    expect(api.unpublish).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();

    complete(grafanaBundle(true).connector);
    await vi.waitFor(() => expect(Array.from(document.querySelectorAll('[role="status"]')).some((status) => status.textContent?.includes('Updating MCP connector'))).toBe(false));
    expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('healthy · published');
    expect(document.querySelector('article')?.textContent).toContain('Published');
    expect(button('Unpublish', document.querySelector('[role="menu"]')!).disabled).toBe(false);
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  test.each([
    { error: new NetworkError(new Error('private diagnostic')), message: 'outcome is unknown' },
    { error: new HttpError(409, '', { detail: { code: 'public_tool_name_conflict', message: 'conflict', phase: 'publication', retryable: false, context: {} } }), message: 'Publication conflicts with an existing public tool name.' },
    { error: new HttpError(401, '', {}), message: 'Administration access was lost' }
  ])('presents publication errors without silently retrying', async ({ error, message }): Promise<void> => {
    const { api, navigate } = renderWorkspace(false);
    api.publish.mockRejectedValue(error);
    const dialog = await openConfirmation('Publish');

    button('Publish', dialog).click();
    await tick();

    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')?.textContent).toContain(message));
    expect(document.body.textContent).not.toContain('private diagnostic');
    expect(api.publish).toHaveBeenCalledOnce();
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(document.querySelector('[role="status"]')).toBeNull();
  });
});
