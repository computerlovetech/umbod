import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { goto } from '$app/navigation';
import * as adminApiModule from '#lib/admin/infrastructure/admin-api.js';
import { InMemoryPersonalOAuthSetup, setupFixture } from '#lib/admin/personal-mcp-servers/setup.test-support.js';
import { InMemoryPersonalServers } from '#lib/admin/personal-mcp-servers/in-memory.js';
import { policyFixture, serverFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { HttpError, NetworkError } from '#lib/admin/infrastructure/transport.js';
import type { DownstreamMcpConnectorsRoute } from '#lib/admin/downstream-mcp-connectors-api.js';
import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceBundle } from './downstream-mcp-workspace-state.svelte';

const navigationPage = vi.hoisted(() => ({ shallow: null as { url: URL } | null }));
vi.mock('$app/state', () => ({ page: {
  url: new URL('http://localhost/admin/downstream-mcp-connectors?capability=tools'),
  get shallow(): { url: URL } | null { return navigationPage.shallow; }
} }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), refreshAll: vi.fn() }));
vi.mock('#lib/components/feedback/index.js', () => ({ useToast: (): object => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }) }));

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
  navigationPage.shallow = null;
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

test('shallow capability navigation uses the selected connector URL rather than the last loaded page URL', async (): Promise<void> => {
  navigationPage.shallow = { url: new URL('http://localhost/admin/downstream-mcp-connectors?connector=grafana&capability=prompts') };
  vi.mocked(goto).mockResolvedValue(undefined);
  renderWorkspace(false);
  expect(document.querySelector('nav[aria-label="Connector capabilities"] a[aria-current="page"]')?.textContent).toContain('Prompts');
  const resources = document.querySelector<HTMLAnchorElement>('nav[aria-label="Connector capabilities"] a[href*="capability=resources"]');
  expect(resources).not.toBeNull();
  resources!.click();
  await tick();
  expect(goto).toHaveBeenCalledWith(new URL('http://localhost/admin/downstream-mcp-connectors?connector=grafana&capability=resources'), { shallow: true, state: {} });
});

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

async function renderPersonalWorkspace(validated: boolean = true, name: string = 'Personal server', published: boolean = false): Promise<{
  composite: adminApiModule.AdminApi;
  state: DownstreamMcpWorkspaceState;
  operations: DownstreamMcpMutationState;
  api: ReturnType<typeof mutationApi>;
  navigate: ReturnType<typeof vi.fn>;
}> {
  const connector = { ...serverFixture(), display_name: name, publication_status: published ? 'published' as const : 'unpublished' as const };
  const personalApi = new InMemoryPersonalServers([connector], [policyFixture()]);
  const composite = new adminApiModule.AdminApi({ request: vi.fn().mockRejectedValue(new Error('Unexpected transport request')) });
  vi.spyOn(composite.personalServers, 'get').mockImplementation((id) => personalApi.get(id));
  vi.spyOn(composite.personalServers, 'policy').mockImplementation((id) => personalApi.policy(id));
  vi.spyOn(composite.personalServers, 'replacePolicy').mockImplementation((id, input) => personalApi.replacePolicy(id, input));
  const setup = new InMemoryPersonalOAuthSetup();
  if (validated) setup.current = setup.validation;
  vi.spyOn(composite.personalOAuthSetup, 'status').mockImplementation((id) => setup.status(id));
  vi.spyOn(composite.personalOAuthSetup, 'validate').mockImplementation((id, input) => setup.validate(id, input));
  vi.spyOn(composite.personalOAuthSetup, 'discover').mockImplementation((id, input) => setup.discover(id, input));
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
  test('personal publication names the pending connector and discloses access details on demand', async (): Promise<void> => {
    const name = 'Records & reports';
    const { api } = await renderPersonalWorkspace(true, name);
    button(`Open actions for ${name}`).click();
    await tick();
    button('Publish', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('dialog');
    if (!dialog) throw new Error('Publication confirmation is missing');
    expect(dialog.querySelector('h2')?.textContent).toBe('Publish connector?');
    expect(dialog.querySelector('.identity strong')?.textContent).toBe(name);
    expect(dialog.querySelector('small')?.textContent).toBe('Personal MCP connector');
    const notice = document.getElementById(dialog.getAttribute('aria-describedby') ?? '');
    expect(notice).not.toBeNull();
    expect(notice?.closest('details')).toBeNull();
    expect(notice?.querySelector('strong')?.textContent).toBe('This changes who can use it');
    expect(notice?.querySelector('p')?.textContent).toBe('Permitted groups can use all its tools, including future tools after discovery.');
    const details = dialog.querySelector('details');
    if (!details) throw new Error('Access details are missing');
    expect(details.open).toBe(false);
    const summary = details.querySelector('summary');
    if (!summary) throw new Error('Access details summary is missing');
    expect(summary.textContent).toBe('Access & setup details');
    summary.click();
    await tick();
    expect(details.open).toBe(true);
    expect(details.querySelector('p')?.textContent).toBe('This does not make the connector available to everyone. Account authorization, owner enablement, and tool discovery remain separate steps.');
    expect(dialog.querySelector('[data-dialog-cancel]')).toBe(button('Cancel', dialog));
    expect(document.activeElement).toBe(button('Cancel', dialog));
    expect(api.publish).not.toHaveBeenCalled();
  });

  test.each(['Cancel', 'Close', 'Escape'] as const)('%s dismisses personal publication without publishing', async (dismissal): Promise<void> => {
    const { api, navigate } = await renderPersonalWorkspace();
    const trigger = button('Open actions for Personal server');
    trigger.click();
    await tick();
    button('Publish', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('dialog');
    if (!dialog) throw new Error('Publication confirmation is missing');
    if (dismissal === 'Escape') {
      const cancel = new Event('cancel', { cancelable: true });
      dialog.dispatchEvent(cancel);
      expect(cancel.defaultPrevented).toBe(true);
    } else {
      button(dismissal, dialog).click();
    }
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.unpublish).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  test.each([
    { action: 'Unpublish', published: true, confirm: 'Unpublish', message: 'After catalogue reload, withdrawal prevents new selection.' },
    { action: 'Delete', published: false, confirm: 'Delete server', message: 'This permanently removes the server and saved local authorizations and policy.' }
  ])('personal $action retains generic confirmation', async ({ action, published, confirm, message }): Promise<void> => {
    const { api } = await renderPersonalWorkspace(true, 'Personal server', published);
    button('Open actions for Personal server').click();
    await tick();
    button(action, document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('dialog');
    if (!dialog) throw new Error('Mutation confirmation is missing');
    expect(dialog.querySelector('h2')?.textContent).toBe(`${action} Personal server?`);
    expect(dialog.textContent).toContain(message);
    expect(dialog.querySelector('details')).toBeNull();
    expect(button(confirm, dialog).disabled).toBe(false);
    button('Cancel', dialog).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.unpublish).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  test('unvalidated personal servers have no publication action', async (): Promise<void> => {
    const { api, composite } = await renderPersonalWorkspace(false);
    expect(document.querySelector('[aria-label="Personal OAuth setup"]')).toBeNull();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('Check required');
    expect(composite.personalOAuthSetup.status).toHaveBeenCalledExactlyOnceWith('personal');
    expect(composite.personalOAuthSetup.validate).not.toHaveBeenCalled();
    button('Open actions for Personal server').click();
    await tick();
    const menu = document.querySelector('[role="menu"]');
    expect(menu).not.toBeNull();
    expect(menu?.textContent).not.toContain('Publish');
    expect(button('Edit', menu!).disabled).toBe(false);
    expect(button('Check configuration', menu!).disabled).toBe(false);
    expect(api.publish).not.toHaveBeenCalled();
  });

  test('checks OAuth from the menu and updates sidebar publication eligibility without reloading details', async (): Promise<void> => {
    const { composite, api } = await renderPersonalWorkspace(false);
    const article = document.querySelector('article');
    button('Open actions for Personal server').click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) throw new Error('Configuration check dialog is missing');
    expect(document.querySelector('[role="menu"]')).toBeNull();
    expect(dialog.textContent).not.toContain('Discover settings');
    expect(dialog.textContent).not.toContain('Validate setup');
    await vi.waitFor(() => expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('Configuration ready'));
    expect(dialog.textContent).toContain('Ready to publish');
    expect(composite.personalOAuthSetup.validate).toHaveBeenCalledOnce();
    expect(composite.personalOAuthSetup.discover).not.toHaveBeenCalled();
    expect(api.publish).not.toHaveBeenCalled();
    button('Close', dialog).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.querySelector('article')).toBe(article);
    expect(composite.personalOAuthSetup.status).toHaveBeenCalledTimes(1);
    button('Open actions for Personal server').click();
    await tick();
    expect(button('Publish', document.querySelector('[role="menu"]')!).disabled).toBe(false);
  });

  test('explicit checks lead to publication confirmation without implicit repeats or stacked dialogs', async (): Promise<void> => {
    const { composite, api } = await renderPersonalWorkspace(false);
    const trigger = button('Open actions for Personal server');
    trigger.click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ready to publish'));
    expect(composite.personalOAuthSetup.validate).toHaveBeenCalledOnce();
    button('Publish', document.querySelector('dialog')!).click();
    await tick();
    expect(document.querySelectorAll('dialog')).toHaveLength(1);
    const confirmation = document.querySelector('dialog');
    expect(confirmation?.textContent).toContain('Publish connector?');
    expect(confirmation?.querySelector('.identity strong')?.textContent).toBe('Personal server');
    expect(api.publish).not.toHaveBeenCalled();
    button('Cancel', confirmation!).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
    trigger.click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ready to publish'));
    expect(composite.personalOAuthSetup.validate).toHaveBeenCalledTimes(2);
    button('Publish', document.querySelector('dialog')!).click();
    await tick();
    button('Publish connector', document.querySelector('dialog')!).click();
    await vi.waitFor(() => expect(api.publish).toHaveBeenCalledExactlyOnceWith('personal'));
    await vi.waitFor(() => expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('· published ·'));
    expect(document.querySelector('dialog')).toBeNull();
    trigger.click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await vi.waitFor(() => expect(document.querySelector('dialog')?.textContent).toContain('Configuration ready'));
    expect(button('Done', document.querySelector('dialog')!).disabled).toBe(false);
    expect(composite.personalOAuthSetup.validate).toHaveBeenCalledTimes(3);
    expect(composite.personalOAuthSetup.status).toHaveBeenCalledOnce();
  });

  test.each([false, true])('a failed explicit check blocks publication even when previously validated=%s', async (validated): Promise<void> => {
    const { composite, api } = await renderPersonalWorkspace(validated);
    vi.mocked(composite.personalOAuthSetup.validate).mockRejectedValueOnce(new NetworkError(new Error('private-provider-response')));
    button('Open actions for Personal server').click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) throw new Error('Configuration check dialog is missing');
    await vi.waitFor(() => expect(dialog.textContent).toContain('Check result unavailable'));
    expect(composite.personalOAuthSetup.validate).toHaveBeenCalledOnce();
    expect(dialog.textContent).not.toContain('private-provider-response');
    expect(button('Refresh status', dialog).disabled).toBe(false);
    button('Close', dialog).click();
    await tick();
    button('Open actions for Personal server').click();
    await tick();
    expect(document.querySelector('[role="menu"]')?.textContent).not.toContain('Publish');
    expect(api.publish).not.toHaveBeenCalled();
  });

  test('moving from setup into Edit restores focus to the persistent action trigger on close', async (): Promise<void> => {
    const { composite } = await renderPersonalWorkspace(false);
    vi.mocked(composite.personalOAuthSetup.validate).mockResolvedValueOnce(setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'registration_unavailable' }));
    const trigger = button('Open actions for Personal server');
    trigger.click();
    await tick();
    button('Check configuration', document.querySelector('[role="menu"]')!).click();
    await tick();
    const setupDialog = document.querySelector('[role="dialog"]');
    if (!setupDialog) throw new Error('Configuration check dialog is missing');
    await vi.waitFor(() => expect(setupDialog.textContent).toContain('Changes required'));
    button('Edit settings', setupDialog).click();
    await vi.waitFor(() => expect(document.querySelector<HTMLInputElement>('#personal-name')?.value).toBe('Personal server'));
    const editor = document.querySelector('[role="dialog"]');
    if (!editor) throw new Error('Personal editor is missing');
    expect(editor).not.toBe(setupDialog);
    button('Cancel', editor).click();
    await tick();
    expect(document.querySelector('dialog')).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  test('validated personal publication reconciles in place without testing sign-in', async (): Promise<void> => {
    const { api, navigate } = await renderPersonalWorkspace();
    const workspace = document.querySelector('[aria-label="MCP connectors workspace"]');
    const personalGuidance = document.querySelector('[aria-label="Personal authorization"]');
    button('Open actions for Personal server').click();
    await tick();
    button('Publish', document.querySelector('[role="menu"]')!).click();
    await tick();
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) throw new Error('Publication confirmation is missing');
    const confirm = button('Publish connector', dialog);
    confirm.click();
    confirm.click();
    await vi.waitFor(() => expect(api.publish).toHaveBeenCalledExactlyOnceWith('personal'));
    await vi.waitFor(() => expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('published'));
    expect(document.querySelector('[aria-label="MCP connectors workspace"]')).toBe(workspace);
    expect(document.querySelector('[aria-label="Personal authorization"]')).toBe(personalGuidance);
    expect(document.querySelector('[aria-pressed="true"]')?.textContent).toContain('Configuration ready');
    expect(document.querySelector('[aria-label="Personal OAuth setup"]')).toBeNull();
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
