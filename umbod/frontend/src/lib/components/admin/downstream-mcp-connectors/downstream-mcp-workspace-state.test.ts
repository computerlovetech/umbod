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
    connector: { connector_id: id, display_name: id, tool_name_prefix: id, icon_url: '', capability_description: 'Manage', base_capability_description: 'Manage', effective_capability_description: 'Manage', capability_description_override: { state: 'system', revision: 0 }, endpoint_url: 'https://example.com/mcp', public_path: `/mcp/proxies/${id}`, public_url: `https://agent.test/mcp/proxies/${id}`, auth_mode: 'none', header_type: 'bearer', custom_header_name: null, credential_configured: false, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null } },
    catalog: { discovered_at: null, tools: [{ name: toolName, title: toolName, description: '', input_schema: {}, output_schema: null, activation_status: 'disabled' }] },
    promptCatalog: { prompts: [], available_actions: [] },
    resourceCatalog: { resources: [], availableActions: [] }
  };
}

describe('DownstreamMcpWorkspaceState', () => {
  test('uses a coherent initial bundle without requesting it again', () => {
    const loader = vi.fn();
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader);
    expect(state.bundle?.connector.connector_id).toBe('a');
    expect(state.bundle?.catalog.tools[0]?.name).toBe('a-tool');
    expect(loader).not.toHaveBeenCalled();
  });

  test('loads all uncached bundle catalogs and reuses the cache', async () => {
    const loader = vi.fn(async (id: string) => createBundle(id));
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader);
    state.selectConnector('b');
    expect(state.detailLoading).toBe(true);
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
    expect(state.bundle).toMatchObject({ catalog: { tools: [{ name: 'b-tool' }] }, promptCatalog: { prompts: [], available_actions: [] }, resourceCatalog: { resources: [], availableActions: [] } });
    state.selectConnector('a');
    state.selectConnector('b');
    expect(loader).toHaveBeenCalledOnce();
  });

  test('exposes bundle failure and retries', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('failed'))).mockResolvedValueOnce(createBundle('b'));
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'), loader);
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
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, loader);
    state.selectConnector('a');
    state.selectConnector('b');
    firstA.resolve(createBundle('a', 'stale-success'));
    await Promise.resolve();
    expect(state.bundle).toBeNull();
    b.resolve(createBundle('b'));
    await vi.waitFor(() => expect(state.bundle?.connector.connector_id).toBe('b'));
    state.selectConnector('a');
    expect(state.bundle?.catalog.tools[0]?.name).toBe('stale-success');

    const olderA = deferred<DownstreamMcpWorkspaceBundle>();
    const sameIdLoader = vi.fn().mockReturnValueOnce(olderA.promise).mockReturnValueOnce(newerA.promise);
    const state2 = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, sameIdLoader);
    state2.selectConnector('a');
    state2.retrySelected();
    newerA.resolve(createBundle('a', 'newer'));
    await vi.waitFor(() => expect(state2.bundle?.catalog.tools[0]?.name).toBe('newer'));
    olderA.resolve(createBundle('a', 'older'));
    await Promise.resolve();
    expect(state2.bundle?.catalog.tools[0]?.name).toBe('newer');
  });

  test('reconciles submitted connector tools after selection changes', () => {
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, createBundle('a'));
    state.selectConnector('b');
    state.reconcileTools('a', [{ name: 'a-tool', title: 'a-tool', description: '', input_schema: {}, output_schema: null, activation_status: 'enabled' }]);
    state.selectConnector('a');
    expect(state.bundle?.catalog.tools[0]?.activation_status).toBe('enabled');
  });

  test('shows the bearer credential field only for bearer authentication', () => {
    const state = new DownstreamMcpWorkspaceState();
    state.open('configure', { focus() {} } as unknown as HTMLElement, {
      connector_id: 'payments', display_name: 'Payments', tool_name_prefix: 'Payments', icon_url: '', capability_description: 'Manage payments', base_capability_description: 'Manage payments', effective_capability_description: 'Manage payments', capability_description_override: { state: 'system', revision: 0 }, endpoint_url: 'https://example.com/mcp', public_path: '/mcp/proxies/payments', public_url: 'https://agent.test/mcp/proxies/payments', auth_mode: 'static_bearer', header_type: 'bearer', custom_header_name: null, credential_configured: true, publication_status: 'unpublished', health: { status: 'unknown', checked_at: null, reason: null }
    });
    expect(state.authMode).toBe('static_bearer');
    state.setAuthMode('none');
    expect(state.authMode).toBe('none');
    state.setAuthMode('static_bearer');
    expect(state.authMode).toBe('static_bearer');
  });

  test('opens a connector-keyed capability description modal and closes the menu', () => {
    const loader = async (): Promise<DownstreamMcpWorkspaceBundle> => { throw new BrowserRequestError(404); };
    const state = new DownstreamMcpWorkspaceState(undefined, undefined, undefined, loader);
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
