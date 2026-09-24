import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import type { OpenApiConnectorListItem } from '$lib/admin/openapi-connectors';
import { OpenApiConnectorListState } from './openapi-connector-list-state.svelte';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => { resolve = resolvePromise; });
  return { promise, resolve };
}

function createConnector(overrides: Partial<OpenApiConnectorListItem> = {}): OpenApiConnectorListItem {
  return {
    id: 'connector-a',
    name: 'Connector A',
    toolNamePrefix: 'Connector_A',
    capabilityDescription: 'Manage connector A resources',
    publicationStatus: 'Draft',
    canPublish: true,
    canUnpublish: false,
    canImport: true,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-02T00:00:00Z',
    tools: [],
    ...overrides
  };
}

describe('OpenAPI connector list state', () => {
  test('resolves the first connector when no selection is set', () => {
    const state = new OpenApiConnectorListState();
    const selected = state.resolveSelectedConnector([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    expect(selected?.id).toBe('connector-a');
  });

  test('resolves the connector from the initial id when present', () => {
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-b' });
    const selected = state.resolveSelectedConnector([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    expect(selected?.id).toBe('connector-b');
  });

  test('selects a connector explicitly and clears the visible action', () => {
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a' });
    state.toggleOperations(createConnector());
    state.selectConnector('connector-b');

    expect(state.selectedConnectorId).toBe('connector-b');
    expect(state.view.visibleAction).toBeNull();
  });

  test('toggles the operations action', () => {
    const state = new OpenApiConnectorListState();

    state.toggleOperations(createConnector());
    expect(state.view.visibleAction).toBe('operations');

    state.toggleOperations(createConnector());
    expect(state.view.visibleAction).toBeNull();
  });

  test('loads tools only when operations are opened and reuses the versioned cache', async () => {
    const tool = { operationId: 'listInvoices', method: 'get', path: '/invoices', summary: 'List', description: '', activationStatus: 'disabled' as const, outputSchema: { status: 'not-declared' as const } };
    const loader = vi.fn(async () => [tool]);
    const connector = createConnector();
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a', loadTools: loader });

    expect(loader).not.toHaveBeenCalled();
    state.toggleOperations(connector);
    expect(state.tools.toolsState(connector).status).toBe('loading');
    await vi.waitFor(() => expect(state.tools.toolsState(connector).status).toBe('ready'));
    state.toggleOperations(connector);
    state.toggleOperations(connector);

    expect(loader).toHaveBeenCalledOnce();
  });

  test('loads each selected connector independently and updates activation in cache', async () => {
    const loader = vi.fn(async (id: string) => [{ operationId: id, method: 'get', path: '/', summary: '', description: '', activationStatus: 'disabled' as const, outputSchema: { status: 'not-declared' as const } }]);
    const first = createConnector();
    const second = createConnector({ id: 'connector-b' });
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a', loadTools: loader });

    state.toggleOperations(first);
    await vi.waitFor(() => expect(state.tools.toolsState(first).status).toBe('ready'));
    state.selectConnector(second.id);
    state.toggleOperations(second);
    await vi.waitFor(() => expect(state.tools.toolsState(second).status).toBe('ready'));
    state.tools.setActivation(first, first.id, 'enabled');

    expect(loader).toHaveBeenCalledTimes(2);
    expect(state.tools.toolsState(first).tools[0]?.activationStatus).toBe('enabled');
  });

  test('distinguishes failure from an empty catalog and supports retry', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('unavailable'))).mockResolvedValueOnce([]);
    const connector = createConnector();
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a', loadTools: loader });

    state.toggleOperations(connector);
    await vi.waitFor(() => expect(state.tools.toolsState(connector).status).toBe('failed'));
    state.tools.retry(connector);
    await vi.waitFor(() => expect(state.tools.toolsState(connector)).toEqual({ status: 'ready', tools: [] }));

    expect(loader).toHaveBeenCalledTimes(2);
  });

  test('reloads when the connector updatedAt version changes', async () => {
    const loader = vi.fn(async () => []);
    const original = createConnector();
    const imported = createConnector({ updatedAt: '2026-01-03T00:00:00Z' });
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a', loadTools: loader });

    state.toggleOperations(original);
    await vi.waitFor(() => expect(state.tools.toolsState(original).status).toBe('ready'));
    state.toggleOperations(original);
    state.toggleOperations(imported);
    await vi.waitFor(() => expect(state.tools.toolsState(imported).status).toBe('ready'));

    expect(loader).toHaveBeenCalledTimes(2);
  });

  test('uses initial detail without a duplicate request', () => {
    const detail = createConnector({ name: 'SSR detail' });
    const loader = vi.fn();
    const state = new OpenApiConnectorListState({ initialConnectorId: detail.id, initialDetail: detail, loadDetail: loader });
    expect(state.resolveSelectedConnector([createConnector()])?.name).toBe('SSR detail');
    expect(loader).not.toHaveBeenCalled();
  });

  test('ignores aborted rapid-switch responses and prevents same-ID overwrite', async () => {
    const a = deferred<OpenApiConnectorListItem>();
    const b = deferred<OpenApiConnectorListItem>();
    const loader = vi.fn((id: string) => id === 'a' ? a.promise : b.promise);
    const summaries = [createConnector({ id: 'a', name: 'A' }), createConnector({ id: 'b', name: 'B' })];
    const state = new OpenApiConnectorListState({ initialConnectorId: 'seed', loadDetail: loader });
    state.selectConnector('a');
    state.selectConnector('b');
    a.resolve(createConnector({ id: 'a', name: 'stale A' }));
    await Promise.resolve();
    expect(state.resolveSelectedConnector(summaries)?.id).toBe('b');
    b.resolve(createConnector({ id: 'b', name: 'fresh B' }));
    await vi.waitFor(() => expect(state.resolveSelectedConnector(summaries)?.name).toBe('fresh B'));

    const older = deferred<OpenApiConnectorListItem>();
    const newer = deferred<OpenApiConnectorListItem>();
    const sameLoader = vi.fn().mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const sameState = new OpenApiConnectorListState({ initialConnectorId: 'seed', loadDetail: sameLoader });
    sameState.selectConnector('a');
    sameState.retryDetail();
    newer.resolve(createConnector({ id: 'a', name: 'newer' }));
    await vi.waitFor(() => expect(sameState.resolveSelectedConnector(summaries)?.name).toBe('newer'));
    older.resolve(createConnector({ id: 'a', name: 'older' }));
    await Promise.resolve();
    expect(sameState.resolveSelectedConnector(summaries)?.name).toBe('newer');
  });

  test('keys tools by authoritative detail updatedAt when detail and tools race', async () => {
    const detail = deferred<OpenApiConnectorListItem>();
    const tool = { operationId: 'operation', method: 'get', path: '/', summary: '', description: '', activationStatus: 'disabled' as const, outputSchema: { status: 'not-declared' as const } };
    const state = new OpenApiConnectorListState({ loadDetail: () => detail.promise, loadTools: async () => [tool] });
    const summary = createConnector({ updatedAt: 'old' });
    void state.loadOperations(summary);
    detail.resolve(createConnector({ updatedAt: 'new' }));
    await vi.waitFor(() => expect(state.tools.toolsState(createConnector({ updatedAt: 'new' })).status).toBe('ready'));
    expect(state.tools.toolsState(summary).tools[0]?.operationId).toBe('operation');
  });

  test('applies submitted activation to its connector after selection changes', async () => {
    const tool = { operationId: 'operation', method: 'get', path: '/', summary: '', description: '', activationStatus: 'disabled' as const, outputSchema: { status: 'not-declared' as const } };
    const connector = createConnector({ id: 'a' });
    const state = new OpenApiConnectorListState({ loadTools: async () => [tool] });
    state.toggleOperations(connector);
    await vi.waitFor(() => expect(state.tools.toolsState(connector).status).toBe('ready'));
    state.selectConnector('b');
    state.tools.setActivation(connector, 'operation', 'enabled');
    expect(state.tools.toolsState(connector).tools[0]?.activationStatus).toBe('enabled');
  });

  test('publishes lazy detail through public reactive state and reuses the cache', async () => {
    const summary = createConnector({ id: 'connector-a', name: 'Summary' });
    const detail = createConnector({ id: 'connector-a', name: 'Detailed', updatedAt: '2026-01-04T00:00:00Z' });
    const loader = vi.fn(async (_connectorId: string) => detail);
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-b', loadDetail: loader });

    state.selectConnector(summary.id);
    expect(state.detailLoading).toBe(true);
    await vi.waitFor(() => expect(state.resolveSelectedConnector([summary])?.name).toBe('Detailed'));
    expect(state.detailLoading).toBe(false);

    state.selectConnector('connector-b');
    state.selectConnector(summary.id);
    expect(state.resolveSelectedConnector([summary])?.name).toBe('Detailed');
    expect(loader.mock.calls.filter(([connectorId]) => connectorId === summary.id)).toHaveLength(1);
  });

  test('retries failed detail loading', async () => {
    const detail = createConnector({ name: 'Retried detail' });
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('unavailable'))).mockResolvedValueOnce(detail);
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-b', loadDetail: loader });

    state.selectConnector(detail.id);
    await vi.waitFor(() => expect(state.detailFailed).toBe(true));
    state.retryDetail();
    await vi.waitFor(() => expect(state.resolveSelectedConnector([createConnector()])?.name).toBe('Retried detail'));

    expect(state.detailFailed).toBe(false);
    expect(loader).toHaveBeenCalledTimes(2);
  });

  test('resumes operation loading after retrying failed detail', async () => {
    const connector = createConnector();
    const detailLoader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('unavailable'))).mockResolvedValueOnce(connector);
    const tool = { operationId: 'operation', method: 'get', path: '/', summary: '', description: '', activationStatus: 'disabled' as const, outputSchema: { status: 'not-declared' as const } };
    const toolLoader = vi.fn(async () => [tool]);
    const state = new OpenApiConnectorListState({ loadDetail: detailLoader, loadTools: toolLoader });

    void state.loadOperations(connector);
    await vi.waitFor(() => expect(state.detailFailed).toBe(true));
    state.retryDetail();
    await vi.waitFor(() => expect(state.tools.toolsState(connector).status).toBe('ready'));

    expect(toolLoader).toHaveBeenCalledTimes(1);
    expect(state.tools.toolsState(connector).tools[0]?.operationId).toBe('operation');
  });

  test('falls back to the first connector when the selected connector disappears', () => {
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-b' });
    const selected = state.resolveSelectedConnector([createConnector({ id: 'connector-c', name: 'Connector C' })]);

    expect(selected?.id).toBe('connector-c');
  });

  test('opens row actions without loading operations until requested', () => {
    const loader = vi.fn(async () => []);
    const state = new OpenApiConnectorListState({ loadTools: loader });
    const connector = createConnector({ id: 'connector-b' });

    state.setMenuOpen(connector.id, true);

    expect(state.selectedConnectorId).toBe(connector.id);
    expect(state.view.openMenuConnectorId).toBe(connector.id);
    expect(state.view.visibleAction).toBeNull();
    expect(loader).not.toHaveBeenCalled();

    state.view.closeMenu();

    expect(state.view.openMenuConnectorId).toBeNull();
    expect(state.view.visibleAction).toBeNull();
    expect(loader).not.toHaveBeenCalled();
  });

  test('isolates the capability description modal by connector and closes the menu', () => {
    const state = new OpenApiConnectorListState({ initialConnectorId: 'connector-a' });

    state.setMenuOpen('connector-b', true);
    state.showCapabilityDescription('connector-b');

    expect(state.view.openMenuConnectorId).toBeNull();
    expect(state.view.capabilityDescriptionConnectorId).toBe('connector-b');

    state.selectConnector('connector-a');
    expect(state.view.capabilityDescriptionConnectorId).toBeNull();
  });

});
