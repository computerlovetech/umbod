import { describe, expect, test, vi } from 'vitest';
import type { OpenApiConnectorListItem, OpenApiOperationToolUiModel } from '$lib/admin/openapi-connectors';
import { OpenApiToolCatalogState, type OpenApiToolCatalogDetailAccess } from './openapi-tool-catalog-state.svelte';

function connector(updatedAt = 'old'): OpenApiConnectorListItem {
  return {
    id: 'connector-a', name: 'Connector A', toolNamePrefix: 'Connector_A', capabilityDescription: '', publicationStatus: 'Draft',
    canPublish: true, canUnpublish: false, canImport: true, createdAt: 'created', updatedAt, tools: []
  };
}

function tool(activationStatus: 'enabled' | 'disabled' = 'disabled'): OpenApiOperationToolUiModel {
  return { operationId: 'list', method: 'get', path: '/', summary: '', description: '', activationStatus, outputSchema: { status: 'not-declared' } };
}

describe('OpenApiToolCatalogState', () => {
  test('uses authoritative detail versions and updates activation', async () => {
    let detail: OpenApiConnectorListItem | undefined;
    const access: OpenApiToolCatalogDetailAccess = {
      readDetail: () => detail,
      fetchDetail: async () => {
        detail = connector('new');
        return detail;
      }
    };
    const loader = vi.fn(async () => [tool()]);
    const state = new OpenApiToolCatalogState({ detailAccess: access, loadTools: loader });

    await state.load(connector());
    expect(state.toolsState(connector()).status).toBe('ready');
    state.setActivation(connector(), 'list', 'enabled');
    expect(state.toolsState(connector()).tools[0]?.activationStatus).toBe('enabled');
    expect(loader).toHaveBeenCalledOnce();
  });

  test('protects the cache from stale forced requests and retries failures', async () => {
    let resolveFirst!: (tools: OpenApiOperationToolUiModel[]) => void;
    const first = new Promise<OpenApiOperationToolUiModel[]>((resolve) => { resolveFirst = resolve; });
    const loader = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce([tool('enabled')]);
    const access: OpenApiToolCatalogDetailAccess = { readDetail: () => connector(), fetchDetail: async () => connector() };
    const state = new OpenApiToolCatalogState({ detailAccess: access, loadTools: loader });

    const staleLoad = state.load(connector());
    await state.load(connector(), true);
    resolveFirst([tool('disabled')]);
    await staleLoad;

    expect(state.toolsState(connector()).tools[0]?.activationStatus).toBe('enabled');
  });
});
