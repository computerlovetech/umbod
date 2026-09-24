import { describe, expect, test, vi } from 'vitest';
import { BrowserRequestError } from '$lib/admin/infrastructure/browser-request';
import type { ConnectorListItem } from '$lib/admin/connectors';
import type { ConnectorDetailBundle } from '$lib/admin/connector-details-browser-api';
import { ConnectorListState } from '$lib/components/admin/connectors/connector-list-state.svelte';

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (reason: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function createConnector(overrides: Partial<ConnectorListItem>): ConnectorListItem {
  return {
    id: 'connector-a',
    name: 'Connector A',
    description: 'Connector A description',
    sourceLabel: 'Built-in',
    configureHref: '/admin/connectors/connector-a/configuration',
    publicationStatus: 'Draft',
    isConfigured: true,
    canPublish: true,
    canUnpublish: false,
    tools: [],
    ...overrides
  };
}

function createBundle(connectorId: string, operationName: string, activationStatus: 'enabled' | 'disabled' = 'disabled'): ConnectorDetailBundle {
  return {
    detail: {
      status: 'ready',
      connector: { id: connectorId, name: connectorId, description: '', sourceLabel: 'Built-in', publicationStatus: 'Draft' },
      tools: [{ operationName, label: operationName, description: '', parameters: [], outputSchema: { status: 'not-declared' }, activationStatus }]
    },
    configurationFields: [],
    promptCatalog: {
      prompts: [
        { name: 'summarize', description: 'Summarize', arguments: [], activation_status: 'disabled' }
      ],
      available_actions: ['activate']
    },
    resourceCatalog: {
      resources: [
        { kind: 'resource', name: 'Guide', description: 'Guide', uri: 'kb://guide', activationStatus: 'disabled' }
      ],
      availableActions: ['activate']
    }
  };
}

describe('connector list state', () => {
  test('selects the first connector by default', () => {
    const state = new ConnectorListState([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    expect(state.selectedConnector?.id).toBe('connector-a');
  });

  test('selects a connector explicitly', () => {
    const state = new ConnectorListState([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    state.selectConnector('connector-b');

    expect(state.selectedConnector?.id).toBe('connector-b');
  });

  test('opens row actions and preserves explicit panel behavior', () => {
    const state = new ConnectorListState([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    state.setMenuOpen('connector-b', true);

    expect(state.selectedConnector?.id).toBe('connector-b');
    expect(state.openMenuConnectorId).toBe('connector-b');
    expect(state.visibleAction).toBeNull();

    state.showConfiguration('connector-b');

    expect(state.openMenuConnectorId).toBeNull();
    expect(state.visibleAction).toBe('configuration');
  });

  test('keeps the publication form mounted until confirmation submits it', () => {
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })]);
    state.setMenuOpen('connector-a', true);
    const requestSubmit = vi.fn(() => expect(state.openMenuConnectorId).toBe('connector-a'));
    const form = { requestSubmit } as unknown as HTMLFormElement;

    state.requestPublicationConfirmation(form, 'Connector A', 'Publish');
    expect(state.openMenuConnectorId).toBe('connector-a');

    state.confirmPublication();

    expect(requestSubmit).toHaveBeenCalledOnce();
    expect(state.pendingPublication).toBeNull();
    expect(state.openMenuConnectorId).toBeNull();
  });

  test('opens and closes a connector-keyed capability description modal independently of configuration', () => {
    const state = new ConnectorListState([
      createConnector({ id: 'connector-a' }),
      createConnector({ id: 'connector-b' })
    ]);

    state.setMenuOpen('connector-b', true);
    state.showCapabilityDescription('connector-b');

    expect(state.openMenuConnectorId).toBeNull();
    expect(state.capabilityDescriptionConnectorId).toBe('connector-b');
    expect(state.visibleAction).toBeNull();

    state.closeCapabilityDescription();
    expect(state.capabilityDescriptionConnectorId).toBeNull();

    state.showCapabilityDescription('connector-a');
    state.selectConnector('connector-b');
    expect(state.capabilityDescriptionConnectorId).toBeNull();
  });

  test('tracks unsaved tool activation changes until reset', () => {
    const state = new ConnectorListState([
      createConnector({
        id: 'connector-a',
        tools: [
          {
            operationName: 'tool-a',
            label: 'Tool A',
            description: 'Tool A description',
            parameters: [],
            outputSchema: { status: 'not-declared' },
            activationStatus: 'disabled'
          }
        ]
      })
    ]);

    state.setToolActivation('tool-a', true);

    expect(state.hasUnsavedToolChanges).toBe(true);
    expect(state.selectedToolActivationDraftsJson).toBe('[{"operationName":"tool-a","activationStatus":"enabled"}]');

    state.resetToolActivationDrafts();

    expect(state.hasUnsavedToolChanges).toBe(false);
  });

  test('uses the initial SSR detail without calling the loader', () => {
    const loader = vi.fn();
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })], {
      selectedConnectorId: 'connector-a', initialDetail: createBundle('connector-a', 'seeded'), loadDetail: loader
    });

    expect(state.selectedConnector?.tools[0]?.operationName).toBe('seeded');
    expect(loader).not.toHaveBeenCalled();
  });

  test('loads uncached selection reactively and reuses its cache', async () => {
    const loader = vi.fn(async (id: string) => createBundle(id, `${id}-tool`));
    const state = new ConnectorListState([createConnector({ id: 'connector-a' }), createConnector({ id: 'connector-b' })], { loadDetail: loader });

    state.selectConnector('connector-b');
    expect(state.detailLoading).toBe(true);
    await vi.waitFor(() => expect(state.selectedConnector?.tools[0]?.operationName).toBe('connector-b-tool'));
    state.selectConnector('connector-a');
    await vi.waitFor(() => expect(state.selectedConnector?.tools[0]?.operationName).toBe('connector-a-tool'));
    state.selectConnector('connector-b');

    expect(state.detailLoading).toBe(false);
    expect(loader.mock.calls.filter(([id]) => id === 'connector-b')).toHaveLength(1);
  });

  test('exposes failure and supports retry', async () => {
    const loader = vi.fn().mockRejectedValueOnce(new BrowserRequestError(undefined, new Error('failed'))).mockResolvedValueOnce(createBundle('connector-b', 'retried'));
    const state = new ConnectorListState([createConnector({ id: 'connector-a' }), createConnector({ id: 'connector-b' })], { loadDetail: loader });

    state.selectConnector('connector-b');
    await vi.waitFor(() => expect(state.detailFailed).toBe(true));
    state.retryDetail();
    await vi.waitFor(() => expect(state.selectedConnector?.tools[0]?.operationName).toBe('retried'));
    expect(state.detailFailed).toBe(false);
  });

  test('does not cross-display ignored-abort responses and caches a successful stale response', async () => {
    const a = deferred<ConnectorDetailBundle>();
    const b = deferred<ConnectorDetailBundle>();
    const loader = vi.fn((id: string) => id === 'connector-a' ? a.promise : b.promise);
    const state = new ConnectorListState([createConnector({ id: 'connector-a' }), createConnector({ id: 'connector-b' })], { loadDetail: loader });

    state.selectConnector('connector-a');
    state.selectConnector('connector-b');
    a.resolve(createBundle('connector-a', 'stale-a'));
    await Promise.resolve();
    expect(state.selectedConnector?.id).toBe('connector-b');
    expect(state.selectedConnector?.tools).toEqual([]);
    b.resolve(createBundle('connector-b', 'fresh-b'));
    await vi.waitFor(() => expect(state.selectedConnector?.tools[0]?.operationName).toBe('fresh-b'));
    state.selectConnector('connector-a');
    expect(state.selectedConnector?.tools[0]?.operationName).toBe('stale-a');
    expect(loader).toHaveBeenCalledTimes(2);
  });

  test('prevents an older same-ID response from overwriting a newer response', async () => {
    const older = deferred<ConnectorDetailBundle>();
    const newer = deferred<ConnectorDetailBundle>();
    const loader = vi.fn().mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })], { loadDetail: loader });

    state.selectConnector('connector-a');
    state.retryDetail();
    newer.resolve(createBundle('connector-a', 'newer'));
    await vi.waitFor(() => expect(state.selectedConnector?.tools[0]?.operationName).toBe('newer'));
    older.resolve(createBundle('connector-a', 'older'));
    await Promise.resolve();
    expect(state.selectedConnector?.tools[0]?.operationName).toBe('newer');
  });

  test('reconciles submitted tool mutations after selection changes', async () => {
    const state = new ConnectorListState([createConnector({ id: 'connector-a' }), createConnector({ id: 'connector-b' })], {
      initialDetail: createBundle('connector-a', 'tool-a'), selectedConnectorId: 'connector-a'
    });
    state.setToolActivation('tool-a', true);
    const submission = state.captureToolActivationSubmission();
    state.selectConnector('connector-b');
    state.markToolActivationsSaved(submission!.connectorId, submission!.changes);
    state.selectConnector('connector-a');

    expect(state.selectedConnector?.tools[0]?.activationStatus).toBe('enabled');
  });

  test('reconciles authoritative partial policy success while preserving applicable activation drafts', () => {
    const bundle = createBundle('connector-a', 'tool-a');
    bundle.invocationPolicies = [{ tool_id: 'tool-a', mode: 'direct', revision: 1 }];
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })], { initialDetail: bundle, selectedConnectorId: 'connector-a' });
    state.setPolicy('tool-a', 'ask');
    state.setToolActivation('tool-a', true);

    state.reconcileAuthoritativePolicies([{ tool_id: 'tool-a', mode: 'ask', revision: 2 }]);
    state.reconcileAuthoritativeActivations('connector-a', [{ tool_id: 'tool-a', activation_status: 'disabled' }]);

    expect(state.changedPolicies).toEqual([]);
    expect(state.invocationPoliciesJson).toBe('{"tools":[]}');
    expect(state.toolActivationIsEnabled('tool-a')).toBe(true);
  });

  test('restores invocation policies when switching back to a cached connector', async () => {
    const loader = vi.fn(async (id: string) => {
      const bundle = createBundle(id, `${id}-tool`);
      bundle.invocationPolicies = [{ tool_id: `${id}-tool`, mode: 'direct', revision: 1 }];
      return bundle;
    });
    const state = new ConnectorListState([createConnector({ id: 'connector-a' }), createConnector({ id: 'connector-b' })], { loadDetail: loader });

    state.selectConnector('connector-a');
    await vi.waitFor(() => expect(state.policies['connector-a-tool']).toBeDefined());
    state.selectConnector('connector-b');
    await vi.waitFor(() => expect(state.policies['connector-b-tool']).toBeDefined());
    state.selectConnector('connector-a');

    expect(state.policies['connector-a-tool']).toEqual({ tool_id: 'connector-a-tool', mode: 'direct', revision: 1 });
  });

  test('falls back to the first connector when the selected connector disappears', () => {
    const state = new ConnectorListState([
      createConnector({ id: 'connector-a', name: 'Connector A' }),
      createConnector({ id: 'connector-b', name: 'Connector B' })
    ]);

    state.selectConnector('connector-b');
    state.replaceConnectors([createConnector({ id: 'connector-c', name: 'Connector C' })]);

    expect(state.selectedConnector?.id).toBe('connector-c');
  });

  test('prompt activation toggle creates dirty payload and mark saved clears dirty', () => {
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })], {
      initialDetail: createBundle('connector-a', 'tool-a'),
      selectedConnectorId: 'connector-a'
    });

    state.setPromptActivation('summarize', true);
    expect(state.hasUnsavedPromptChanges).toBe(true);
    expect(JSON.parse(state.selectedPromptActivationDraftsJson)).toEqual([
      { promptId: 'summarize', activationStatus: 'enabled' }
    ]);

    state.markPromptActivationsSaved('connector-a', { summarize: 'enabled' });
    expect(state.hasUnsavedPromptChanges).toBe(false);
    expect(state.promptActivationIsEnabled('summarize')).toBe(true);
  });

  test('resource activation toggle creates dirty payload and mark saved clears dirty', () => {
    const state = new ConnectorListState([createConnector({ id: 'connector-a' })], {
      initialDetail: createBundle('connector-a', 'tool-a'),
      selectedConnectorId: 'connector-a'
    });

    state.setResourceActivation('kb://guide', 'resource', true);
    expect(state.hasUnsavedResourceChanges).toBe(true);
    expect(JSON.parse(state.selectedResourceActivationDraftsJson)).toEqual([
      { resourceId: 'kb://guide', kind: 'resource', activationStatus: 'enabled' }
    ]);

    state.markResourceActivationsSaved('connector-a', { 'resource:kb://guide': 'enabled' });
    expect(state.hasUnsavedResourceChanges).toBe(false);
    expect(state.resourceActivationIsEnabled('kb://guide', 'resource')).toBe(true);
  });
});
