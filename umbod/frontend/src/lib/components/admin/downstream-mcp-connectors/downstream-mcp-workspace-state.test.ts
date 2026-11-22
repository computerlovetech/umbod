import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '#lib/admin/infrastructure/transport.js';
import { policyFixture, serverFixture, summaryFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { InMemoryPersonalOAuthSetup } from '#lib/admin/personal-mcp-servers/setup.test-support.js';
import type { SetupStatus } from '#lib/admin/personal-mcp-servers/domain/setup.js';
import * as adminApiModule from '#lib/admin/infrastructure/admin-api.js';
import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '#lib/admin/infrastructure/browser-request.js';
import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceBundle } from './downstream-mcp-workspace-state.svelte';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

function createBundle(id: string, toolName = `${id}-tool`): DownstreamMcpWorkspaceBundle {
  return {
    mode: 'shared',
    connector: { connector_id: id, display_name: id, tool_name_prefix: id, icon_url: '', capability_description: 'Manage', base_capability_description: 'Manage', effective_capability_description: 'Manage', capability_description_override: { state: 'system', revision: 0 }, endpoint_url: 'https://example.com/mcp', public_path: `/mcp/proxies/${id}`, public_url: `https://agent.test/mcp/proxies/${id}`, auth_mode: 'none', authorization_mode: 'shared', header_type: 'bearer', custom_header_name: null, credential_configured: false, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null } },
    catalog: { discovered_at: null, tools: [{ name: toolName, title: toolName, description: '', input_schema: {}, output_schema: null, activation_status: 'disabled' }] },
    promptCatalog: { prompts: [], available_actions: [] },
    resourceCatalog: { resources: [], availableActions: [] }
  };
}

const sharedRows = ['a', 'b', 'orders'].map((connector_id) => ({ connector_id, authorization_mode: 'shared' as const }));

describe('common MCP mutations through the generic administration port', () => {
  function operations(): { api: { publish: ReturnType<typeof vi.fn>; unpublish: ReturnType<typeof vi.fn>; delete: ReturnType<typeof vi.fn>; list: ReturnType<typeof vi.fn> }; state: DownstreamMcpMutationState; navigate: ReturnType<typeof vi.fn> } {
    const api = { publish: vi.fn(async () => ({ connector_id: 'personal', publication_status: 'published' as const })), unpublish: vi.fn(async () => ({ connector_id: 'personal', publication_status: 'unpublished' as const })), delete: vi.fn(async () => {}), list: vi.fn(async () => ({ connectors: [summaryFixture('remaining')] })) };
    const navigate = vi.fn();
    return { api, state: new DownstreamMcpMutationState(api, navigate), navigate };
  }
  test.each(['publish', 'unpublish', 'delete'] as const)('%s is confirmed once, then selects the correct authoritative definition', async (action) => {
    const { api, state, navigate } = operations();
    state.request(action, 'personal', 'Personal');
    expect(api[action]).not.toHaveBeenCalled();
    await state.confirm();
    await state.confirm();
    expect(api[action]).toHaveBeenCalledTimes(1);
    expect(api[action]).toHaveBeenCalledWith('personal');
    if (action === 'delete') {
      expect(navigate).toHaveBeenCalledWith('remaining');
      expect(state.locked).toBe(true);
    } else {
      expect(navigate).not.toHaveBeenCalled();
      expect(api.list).not.toHaveBeenCalled();
      expect(state.publicationStatuses.get('personal')).toBe(action === 'publish' ? 'published' : 'unpublished');
      expect(state.locked).toBe(false);
    }
  });
  test.each([new NetworkError(new Error('secret-sentinel')), new SchemaValidationError('inbound', []), new HttpError(503, '', {})])('uncertain mutation never replays or reintroduces stale inventory before explicit reload', async (error) => {
    const { api, state, navigate } = operations();
    api.delete.mockRejectedValueOnce(error);
    state.request('delete', 'personal', 'Personal');
    await state.confirm();
    state.request('delete', 'personal', 'Personal');
    await state.confirm();
    expect(api.delete).toHaveBeenCalledTimes(1);
    expect(api.list).not.toHaveBeenCalled();
    expect(state.blocked).toBe(true);
    expect(state.message).toContain('outcome is unknown');
    expect(state.message).not.toContain('secret-sentinel');
    state.reload();
    expect(navigate).toHaveBeenCalledOnce();
    expect(state.locked).toBe(true);
  });
  test('grants conflict explains explicit cleanup without removal or retry', async () => {
    const { api, state } = operations();
    api.delete.mockRejectedValueOnce(new HttpError(409, '', { detail: { code: 'downstream_connector_grants_conflict' } }));
    state.request('delete', 'personal', 'Personal');
    await state.confirm();
    expect(state.message).toContain('Permissions');
    expect(state.message).toContain('not retried');
    expect(api.delete).toHaveBeenCalledTimes(1);
    expect(api.list).not.toHaveBeenCalled();
  });
  test.each(['authentication', 'disposal'] as const)('%s fences late common mutation success and authoritative reconciliation', async (reason) => {
    const { api, state, navigate } = operations();
    const pending = deferred<void>();
    api.delete.mockReturnValueOnce(pending.promise);
    state.request('delete', 'personal', 'Personal');
    const operation = state.confirm();
    if (reason === 'authentication') state.loseAccess();
    else state.dispose();
    pending.resolve();
    await operation;
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
    expect(state.pending).toBeNull();
    state.request('publish', 'personal', 'Personal');
    await state.confirm();
    expect(api.publish).not.toHaveBeenCalled();
  });
  test.each(['authentication', 'disposal'] as const)('%s fences late publication status updates', async (reason): Promise<void> => {
    const { api, state, navigate } = operations();
    const pending = deferred<{ connector_id: string; publication_status: 'published' }>();
    api.publish.mockReturnValueOnce(pending.promise);
    state.request('publish', 'personal', 'Personal');
    const operation = state.confirm();
    if (reason === 'authentication') state.loseAccess();
    else state.dispose();

    pending.resolve({ connector_id: 'personal', publication_status: 'published' });
    await operation;

    expect(state.publicationStatuses.size).toBe(0);
    expect(api.list).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
  test('authentication rejection prevents reload or mutation replay', async () => {
    const { api, state, navigate } = operations();
    api.publish.mockRejectedValueOnce(new AuthenticationRequiredError());
    state.request('publish', 'personal', 'Personal');
    await state.confirm();
    state.reload();
    state.request('publish', 'personal', 'Personal');
    await state.confirm();
    expect(state.authenticationLost).toBe(true);
    expect(navigate).not.toHaveBeenCalled();
    expect(api.publish).toHaveBeenCalledTimes(1);
  });
  test('registration and policy lock sources aggregate independently', () => {
    const { state } = operations();
    state.setRegistrationLocked(true);
    state.setFormLocked(true);
    state.setFormLocked(false);
    expect(state.locked).toBe(true);
    state.setFormLocked(true);
    state.setRegistrationLocked(false);
    expect(state.locked).toBe(true);
    state.setFormLocked(false);
    expect(state.locked).toBe(false);
  });
  test('policy uncertainty or activity blocks competing common changes until explicit policy reconciliation', () => {
    const { api, state } = operations();
    state.setFormLocked(true);
    state.request('publish', 'personal', 'Personal');
    expect(state.pending).toBeNull();
    expect(api.publish).not.toHaveBeenCalled();
    state.setFormLocked(false);
    state.request('publish', 'personal', 'Personal');
    expect(state.pending?.id).toBe('personal');
  });
});

describe('DownstreamMcpWorkspaceState', () => {
  test('starts with the source chooser and restores focus when dismissed', () => {
    const state = new DownstreamMcpWorkspaceState();
    const focus = vi.fn();
    const trigger = { focus } as unknown as HTMLElement;

    state.beginCreate(trigger);

    expect(state.modal).toBe('choose');
    expect(state.returnFocus).toBe(trigger);
    state.close();
    expect(focus).toHaveBeenCalledOnce();
  });

  test('does not start creation while locked', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.operations.setRegistrationLocked(true);

    state.beginCreate({ focus: vi.fn() } as unknown as HTMLElement);

    expect(state.modal).toBeNull();
    expect(state.returnFocus).toBeNull();
  });

  test('hands off a registry selection to the existing shared form without using old errors', () => {
    const state = new DownstreamMcpWorkspaceState();
    const previousForm = { mode: 'create', message: 'Previous error' };
    const draft = { displayName: 'Project Tools', description: 'Project search', endpointUrl: 'https://tools.example/mcp' };
    state.beginCreate({ focus: vi.fn() } as unknown as HTMLElement, previousForm);
    state.completeSharedSetup('static_bearer', draft);

    expect(state.modal).toBe('create');
    expect(state.createDraft).toEqual(draft);
    expect(state.authMode).toBe('static_bearer');
    expect(state.createPublicPath).toBe('project-tools');
    expect(state.currentForm(previousForm)).toBeUndefined();
    const nextForm = { mode: 'create', message: 'Current error' };
    expect(state.currentForm(nextForm)).toBe(nextForm);

    state.returnToAccess();
    expect(state.modal).toBe('choose');
    state.completeSharedSetup('none', draft);
    expect(state.modal).toBe('create');
    expect(state.createDraft).toEqual(draft);
    expect(state.authMode).toBe('none');
  });

  test('does not hand off a wizard result after the wizard is closed', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.beginCreate({ focus: vi.fn() } as unknown as HTMLElement);
    state.close();
    state.completeSharedSetup('none', { displayName: '', description: '', endpointUrl: 'https://tools.example/mcp' });

    expect(state.modal).toBeNull();
    expect(state.createDraft).toBeUndefined();
  });

  test('uses a coherent initial bundle without requesting it again', () => {
    const loader = vi.fn();
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, sharedRows);
    expect(state.bundle?.connector.connector_id).toBe('a');
    expect(state.bundle?.catalog?.tools[0]?.name).toBe('a-tool');
    expect(loader).not.toHaveBeenCalled();
  });

  test('loads all uncached bundle catalogs and reuses the cache', async () => {
    const loader = vi.fn(async (id: string) => createBundle(id));
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, sharedRows);
    state.selectConnector('b');
    expect(state.detailLoading).toBe(true);
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
    expect(state.bundle).toMatchObject({ catalog: { tools: [{ name: 'b-tool' }] }, promptCatalog: { prompts: [], available_actions: [] }, resourceCatalog: { resources: [], availableActions: [] } });
    state.selectConnector('a');
    state.selectConnector('b');
    expect(loader).toHaveBeenCalledOnce();
  });

  test('detail authentication loss hides cached definitions and prevents switching them back into view', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new AuthenticationRequiredError());
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, sharedRows);
    state.selectConnector('b');
    await vi.waitFor(() => expect(state.operations.authenticationLost).toBe(true));
    state.selectConnector('a');
    expect(state.selectedConnectorId).toBe('b');
    expect(state.bundle).toBeNull();
    expect(loader).toHaveBeenCalledOnce();
  });

  test('exposes bundle failure and retries', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('failed'))).mockResolvedValueOnce(createBundle('b'));
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, sharedRows);
    state.selectConnector('b');
    await vi.waitFor(() => expect(state.detailFailed).toBe(true));
    state.retrySelected();
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
    expect(state.detailFailed).toBe(false);
  });

  test('prevents cross-display, caches stale success, and prevents same-ID overwrite', async () => {
    const firstA = deferred<DownstreamMcpWorkspaceBundle>();
    const b = deferred<DownstreamMcpWorkspaceBundle>();
    const newerA = deferred<DownstreamMcpWorkspaceBundle>();
    const loader = vi.fn().mockReturnValueOnce(firstA.promise).mockReturnValueOnce(b.promise).mockReturnValueOnce(newerA.promise);
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, loader, undefined, undefined, sharedRows);
    state.selectConnector('a');
    state.selectConnector('b');
    firstA.resolve(createBundle('a', 'stale-success'));
    await Promise.resolve();
    expect(state.bundle).toBeNull();
    b.resolve(createBundle('b'));
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
    state.selectConnector('a');
    expect(state.bundle?.catalog?.tools[0]?.name).toBe('stale-success');

    const olderA = deferred<DownstreamMcpWorkspaceBundle>();
    const sameIdLoader = vi.fn().mockReturnValueOnce(olderA.promise).mockReturnValueOnce(newerA.promise);
    const state2 = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, sameIdLoader, undefined, undefined, sharedRows);
    state2.selectConnector('a');
    state2.retrySelected();
    newerA.resolve(createBundle('a', 'newer'));
    await vi.waitFor(() => expect(state2.bundle?.catalog?.tools[0]?.name).toBe('newer'));
    olderA.resolve(createBundle('a', 'older'));
    await Promise.resolve();
    expect(state2.bundle?.catalog?.tools[0]?.name).toBe('newer');
  });

  test('reconciles submitted connector tools after selection changes', (): void => {
    const loader = vi.fn(async (id: string): Promise<DownstreamMcpWorkspaceBundle> => createBundle(id));
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, sharedRows);
    state.selectConnector('b');
    expect(state.selectedConnectorId).toBe('b');
    state.reconcileTools('a', [{ name: 'a-tool', title: 'a-tool', description: '', input_schema: {}, output_schema: null, activation_status: 'enabled' }]);
    state.selectConnector('a');
    expect(state.bundle?.catalog?.tools[0]?.activation_status).toBe('enabled');
  });

  test('accepts personal details through the same selector but refuses shared configuration', async () => {
    const personal: DownstreamMcpWorkspaceBundle = { mode: 'personal', connector: { ...createBundle('personal').connector, authorization_mode: 'personal', auth_mode: 'oauth' } };
    const loader = vi.fn(async () => personal);
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, [...sharedRows, personal.connector]);
    state.selectConnector('personal');
    await vi.waitFor(() => expect(state.bundle?.mode).toBe('personal'));
    expect(state.selectedConnectorId).toBe('personal');
    expect(state.bundle?.catalog).toBeUndefined();
    state.open('configure', { focus() {} } as unknown as HTMLElement, personal.connector);
    expect(state.modal).toBeNull();
    state.selectConnector('a');
    expect(state.bundle?.mode).toBe('shared');
    state.selectConnector('unknown');
    expect(state.selectedConnectorId).toBe('a');
  });

  test('personal and shared in-flight responses cannot cross-display', async () => {
    const personal = deferred<DownstreamMcpWorkspaceBundle>();
    const shared = deferred<DownstreamMcpWorkspaceBundle>();
    const loader = vi.fn().mockReturnValueOnce(personal.promise).mockReturnValueOnce(shared.promise);
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader, undefined, undefined, [...sharedRows, { connector_id: 'personal' }]);
    state.selectConnector('personal');
    state.selectConnector('b');
    personal.resolve({ mode: 'personal', connector: { ...createBundle('personal').connector, authorization_mode: 'personal', auth_mode: 'oauth' } });
    await Promise.resolve();
    expect(state.bundle).toBeNull();
    shared.resolve(createBundle('b'));
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
  });

  test('shows the bearer credential field only for bearer authentication', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.open('configure', { focus() {} } as unknown as HTMLElement, {
      connector_id: 'payments', display_name: 'Payments', tool_name_prefix: 'Payments', icon_url: '', capability_description: 'Manage payments', base_capability_description: 'Manage payments', effective_capability_description: 'Manage payments', capability_description_override: { state: 'system', revision: 0 }, endpoint_url: 'https://example.com/mcp', public_path: '/mcp/proxies/payments', public_url: 'https://agent.test/mcp/proxies/payments', auth_mode: 'static_bearer', authorization_mode: 'shared', header_type: 'bearer', custom_header_name: null, credential_configured: true, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null }
    });
    expect(state.authMode).toBe('static_bearer');
    state.setAuthMode('none');
    expect(state.authMode).toBe('none');
    state.setAuthMode('static_bearer');
    expect(state.authMode).toBe('static_bearer');
  });

  test('opens a connector-keyed capability description modal and closes the menu', () => {
    const loader = async (): Promise<DownstreamMcpWorkspaceBundle> => { throw new BrowserRequestError(404); };
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, loader, undefined, undefined, sharedRows);
    const trigger = { focus() {} } as unknown as HTMLElement;
    state.setMenuOpen(true);

    state.openCapabilityDescription('payments', trigger);

    expect(state.menuOpen).toBe(false);
    expect(state.capabilityDescriptionConnectorId).toBe('payments');
    expect(state.modal).toBeNull();

    state.selectConnector('orders');
    expect(state.capabilityDescriptionConnectorId).toBeNull();
  });

  test.each(['published', 'unpublished'] as const)('requests confirmation for a %s connector without retaining a menu form', (publication_status): void => {
    const state = new DownstreamMcpWorkspaceState();
    state.setMenuOpen(true);

    state.requestPublication({ ...createBundle('payments').connector, publication_status });

    expect(state.menuOpen).toBe(false);
    expect(state.operations.pending).toEqual({ action: publication_status === 'published' ? 'unpublish' : 'publish', id: 'payments', name: 'payments' });
    state.operations.cancel();
    expect(state.operations.pending).toBeNull();
  });

  test('personal readiness reads leave creation available and preserve independent mutation locks', async (): Promise<void> => {
    const connector = serverFixture();
    const setup = new InMemoryPersonalOAuthSetup();
    const status = deferred<SetupStatus>();
    const validation = deferred<SetupStatus>();
    const api = new adminApiModule.AdminApi({ request: vi.fn().mockRejectedValue(new Error('Unexpected transport request')) });
    vi.spyOn(api.personalServers, 'policy').mockResolvedValue(policyFixture());
    vi.spyOn(api.personalServers, 'get').mockResolvedValue(connector);
    vi.spyOn(api.personalOAuthSetup, 'status').mockReturnValue(status.promise);
    vi.spyOn(api.personalOAuthSetup, 'validate').mockReturnValue(validation.promise);
    const apiFactory = vi.spyOn(adminApiModule, 'adminApi').mockReturnValue(api);
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, { mode: 'personal', connector });
    apiFactory.mockRestore();

    const loading = state.personalSetup.load(connector.connector_id);
    expect(state.personalSetup.outcome).toBe('loading');
    expect(state.operations.locked).toBe(false);
    state.requestPublication(connector);
    expect(state.operations.pending).toBeNull();
    state.beginCreate({ focus: vi.fn() } as unknown as HTMLElement);
    expect(state.modal).toBe('choose');
    state.close();

    state.operations.setFormLocked(true);
    status.resolve(setup.current);
    await loading;
    expect(state.operations.locked).toBe(true);
    expect(state.operations.canPublish(connector)).toBe(false);
    state.operations.setFormLocked(false);

    const checking = state.personalSetup.check();
    expect(state.operations.locked).toBe(true);
    state.operations.setFormLocked(true);
    state.operations.setFormLocked(false);
    expect(state.operations.locked).toBe(true);
    state.operations.setFormLocked(true);
    validation.resolve(setup.validation);
    await checking;
    expect(state.operations.locked).toBe(true);

    state.operations.setFormLocked(false);
    expect(state.operations.locked).toBe(false);
    state.requestPublication(connector);
    expect(state.operations.pending?.action).toBe('publish');
  });

  test('personal publication requires current validation while published servers remain withdrawable', (): void => {
    const state = new DownstreamMcpWorkspaceState();
    const connector = summaryFixture();
    state.requestPublication(connector);
    expect(state.operations.pending).toBeNull();
    state.operations.setPersonalValidation(connector.connector_id, true);
    state.requestPublication(connector);
    expect(state.operations.pending?.action).toBe('publish');
    state.operations.setPersonalValidation(connector.connector_id, false);
    expect(state.operations.pending).toBeNull();
    state.requestPublication({ ...connector, publication_status: 'published' });
    expect(state.operations.pending?.action).toBe('unpublish');
  });

  test('changing selection cancels pending publication', (): void => {
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), undefined, undefined, undefined, sharedRows);
    state.requestPublication(createBundle('a').connector);

    state.selectConnector('b');

    expect(state.operations.pending).toBeNull();
  });

  test('creates a stable public path slug suggestion', (): void => {
    const state = new DownstreamMcpWorkspaceState();
    state.open('create', { focus(): void {} } as unknown as HTMLElement);
    state.updateDisplayName({ currentTarget: { value: '  Payments API / EU ' } } as unknown as Event);
    expect(state.createPublicPath).toBe('payments-api-eu');
  });

  test('restores a failed create submission in the open modal', () => {
    const state = new DownstreamMcpWorkspaceState('create', {
      displayName: 'Computerlove Tech',
      toolNamePrefix: 'Computerlove_Tech',
      capabilityDescription: 'Manage Computerlove tools',
      endpointUrl: 'https://mcp.example.com/mcp',
      publicPath: '/mcp',
      authMode: 'none'
    });
    expect(state.modal).toBe('create');
    expect(state.createPublicPath).toBe('mcp');
    expect(state.publicPathEdited).toBe(true);
  });

  test('suggests a backend-compatible proxy path and preserves explicit edits', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.open('create', { focus() {} } as unknown as HTMLElement);
    state.updateDisplayName({ currentTarget: { value: 'Payment Service' } } as unknown as Event);
    expect(state.createPublicPath).toBe('payment-service');
    expect(state.toolNamePrefix).toBe('Payment_Service');
    state.updatePublicPath({ currentTarget: { value: 'custom' } } as unknown as Event);
    state.updateToolNamePrefix({ currentTarget: { value: 'custom_prefix' } } as unknown as Event);
    state.updateDisplayName({ currentTarget: { value: 'Changed' } } as unknown as Event);
    expect(state.createPublicPath).toBe('custom');
    expect(state.toolNamePrefix).toBe('custom_prefix');
  });
});
