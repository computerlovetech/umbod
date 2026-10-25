import { DownstreamMcpMutationState } from './downstream-mcp-mutation-state.svelte';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { summaryFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import { DownstreamMcpWorkspaceState, suggestedConnectorId, type DownstreamMcpWorkspaceBundle } from './downstream-mcp-workspace-state.svelte';

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
    expect(navigate).toHaveBeenCalledWith(action === 'delete' ? 'remaining' : 'personal');
    expect(state.locked).toBe(true);
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
    expect(state.message).toContain('Group permissions');
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
  test.each([
    { registration: 'disabled', authorization: 'disabled', expected: 'create' },
    { registration: 'unknown', authorization: 'unknown', expected: 'create' },
    { registration: 'enabled', authorization: 'enabled', expected: 'choose' },
    { registration: 'enabled', authorization: 'disabled', expected: 'choose' }
  ] as const)('starts $expected when registration is $registration and OAuth is $authorization', ({ registration, authorization, expected }) => {
    const state = new DownstreamMcpWorkspaceState();
    const focus = vi.fn();
    const trigger = { focus } as unknown as HTMLElement;

    state.beginCreate({ registration, authorization }, trigger);

    expect(state.modal).toBe(expected);
    expect(state.returnFocus).toBe(trigger);
    state.close();
    expect(focus).toHaveBeenCalledOnce();
  });

  test.each(['enabled', 'disabled', 'unknown'] as const)('does not start creation while locked with %s registration', (registration) => {
    const state = new DownstreamMcpWorkspaceState();
    state.operations.setRegistrationLocked(true);

    state.beginCreate({ registration, authorization: 'enabled' }, { focus: vi.fn() } as unknown as HTMLElement);

    expect(state.modal).toBeNull();
    expect(state.returnFocus).toBeNull();
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

  test('reconciles submitted connector tools after selection changes', () => {
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'));
    state.selectConnector('b');
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

  test('requests, cancels, and confirms publication through the stored form', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.setMenuOpen(true);
    let submissions = 0;
    const form = { requestSubmit: () => {
      expect(state.menuOpen).toBe(true);
      submissions += 1;
    } } as unknown as HTMLFormElement;

    state.requestPublicationConfirmation(form, 'Payments', 'Publish');
    expect(state.menuOpen).toBe(true);
    expect(state.pendingPublication?.connectorName).toBe('Payments');
    expect(state.pendingPublication?.actionLabel).toBe('Publish');

    state.cancelPublication();
    expect(state.pendingPublication).toBeNull();
    expect(state.menuOpen).toBe(false);
    expect(submissions).toBe(0);

    state.setMenuOpen(true);
    state.requestPublicationConfirmation(form, 'Payments', 'Unpublish');
    state.confirmPublication();
    expect(state.pendingPublication).toBeNull();
    expect(state.menuOpen).toBe(false);
    expect(submissions).toBe(1);
  });

  test('creates a stable public path slug suggestion', () => {
    expect(suggestedConnectorId('  Payments API / EU ')).toBe('payments-api-eu');
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
