import type { OpenApiOperationToolUiModel } from '$lib/admin/openapi-connectors';
import { describe, expect, test } from 'vitest';
import { OpenApiOperationCatalogState } from './openapi-operation-catalog-state.svelte';

function createTool(
  index: number,
  overrides: Partial<OpenApiOperationToolUiModel> = {}
): OpenApiOperationToolUiModel {
  return {
    operationId: `operation-${index}`,
    method: 'get',
    path: `/resources/${index}`,
    summary: `Resource ${index}`,
    description: `Description ${index}`,
    activationStatus: 'disabled',
    outputSchema: { status: 'not-declared' },
    ...overrides
  };
}

function createTools(count: number): OpenApiOperationToolUiModel[] {
  return Array.from({ length: count }, (_, index) => createTool(index + 1));
}

function operationIds(tools: OpenApiOperationToolUiModel[]): string[] {
  return tools.map((tool) => tool.operationId);
}

describe('OpenApiOperationCatalogState', () => {
  test('defaults to the first 20 operations and reports navigation availability', () => {
    const state = new OpenApiOperationCatalogState(createTools(45));

    expect(state.pageSize).toBe(20);
    expect(state.page).toBe(1);
    expect(state.paginatedTools).toHaveLength(20);
    expect(operationIds(state.paginatedTools)).toEqual(
      Array.from({ length: 20 }, (_, index) => `operation-${index + 1}`)
    );
    expect(state.canGoPrevious).toBe(false);
    expect(state.canGoNext).toBe(true);
  });

  test.each([
    { pageSize: 20 as const, expectedLength: 20, lastOperation: 'operation-20' },
    { pageSize: 50 as const, expectedLength: 50, lastOperation: 'operation-50' },
    { pageSize: 100 as const, expectedLength: 100, lastOperation: 'operation-100' }
  ])('returns the $pageSize operation slice', ({ pageSize, expectedLength, lastOperation }) => {
    const state = new OpenApiOperationCatalogState(createTools(125));

    state.setPageSize(pageSize);

    expect(state.paginatedTools).toHaveLength(expectedLength);
    expect(state.paginatedTools.at(-1)?.operationId).toBe(lastOperation);
  });

  test('stops navigation at the first and last page', () => {
    const state = new OpenApiOperationCatalogState(createTools(41));

    state.previousPage();
    expect(state.page).toBe(1);

    state.nextPage();
    state.nextPage();
    state.nextPage();

    expect(state.page).toBe(3);
    expect(state.paginatedTools).toHaveLength(1);
    expect(state.canGoPrevious).toBe(true);
    expect(state.canGoNext).toBe(false);

    state.previousPage();
    expect(state.page).toBe(2);
  });

  test.each([
    { count: 40, expectedPageCount: 2, expectedLastPageLength: 20 },
    { count: 41, expectedPageCount: 3, expectedLastPageLength: 1 }
  ])('calculates page counts for $count operations', ({ count, expectedPageCount, expectedLastPageLength }) => {
    const state = new OpenApiOperationCatalogState(createTools(count));

    while (state.canGoNext) state.nextPage();

    expect(state.pageCount).toBe(expectedPageCount);
    expect(state.paginatedTools).toHaveLength(expectedLastPageLength);
  });

  test('intersects search, method, and status filters', () => {
    const state = new OpenApiOperationCatalogState([
      createTool(1, { operationId: 'findActiveInvoice', method: 'GET', summary: 'Invoice lookup', activationStatus: 'enabled' }),
      createTool(2, { operationId: 'findDisabledInvoice', method: 'get', summary: 'Invoice lookup', activationStatus: 'disabled' }),
      createTool(3, { operationId: 'createActiveInvoice', method: 'POST', summary: 'Invoice creation', activationStatus: 'enabled' }),
      createTool(4, { operationId: 'findActiveCustomer', method: 'GET', summary: 'Customer lookup', activationStatus: 'enabled' })
    ]);

    state.setSearch('invoice');
    state.setMethodFilter(' get ');
    state.setStatusFilter('enabled');

    expect(operationIds(state.filteredTools)).toEqual(['findActiveInvoice']);
  });

  test('exposes normalized unique sorted methods', () => {
    const state = new OpenApiOperationCatalogState([
      createTool(1, { method: ' post ' }),
      createTool(2, { method: 'GET' }),
      createTool(3, { method: 'get' }),
      createTool(4, { method: ' Delete ' }),
      createTool(5, { method: 'POST' })
    ]);

    expect(state.availableMethods).toEqual(['DELETE', 'GET', 'POST']);
  });

  test('reports total and filtered counts independently', () => {
    const state = new OpenApiOperationCatalogState([
      createTool(1, { method: 'GET', activationStatus: 'enabled' }),
      createTool(2, { method: 'POST', activationStatus: 'disabled' }),
      createTool(3, { method: 'GET', activationStatus: 'disabled' })
    ]);

    state.setMethodFilter('GET');

    expect(state.totalCount).toBe(3);
    expect(state.filteredCount).toBe(2);
  });

  test('resets to page one whenever search, method, status, or page size changes', () => {
    const state = new OpenApiOperationCatalogState(createTools(60));

    state.nextPage();
    state.setSearch('resource');
    expect(state.page).toBe(1);

    state.nextPage();
    state.setMethodFilter('GET');
    expect(state.page).toBe(1);

    state.nextPage();
    state.setStatusFilter('disabled');
    expect(state.page).toBe(1);

    state.nextPage();
    state.setPageSize(50);
    expect(state.page).toBe(1);
  });

  test('updates status-filtered results after activation without changing view state', () => {
    const state = new OpenApiOperationCatalogState([
      ...createTools(25),
      createTool(26, { operationId: 'createInvoice', method: 'POST', summary: 'Invoice creation' })
    ]);
    state.setSearch('invoice');
    state.setMethodFilter('POST');
    state.setStatusFilter('disabled');
    state.setPageSize(50);

    state.setToolActivation('createInvoice', 'enabled');

    expect(state.search).toBe('invoice');
    expect(state.methodFilter).toBe('POST');
    expect(state.statusFilter).toBe('disabled');
    expect(state.pageSize).toBe(50);
    expect(state.page).toBe(1);
    expect(state.filteredTools).toEqual([]);
    expect(state.tools.find((tool) => tool.operationId === 'createInvoice')?.activationStatus).toBe('enabled');
  });

  test('tracks changed activations and commits successful saves', () => {
    const state = new OpenApiOperationCatalogState([createTool(1)]);

    state.setToolActivation('operation-1', 'enabled');

    expect(state.dirty).toBe(true);
    expect(JSON.parse(state.activationRequestJson())).toEqual({ tools: [{ tool_id: 'operation-1', activation_status: 'enabled' }] });

    state.beginSave();
    state.setToolActivation('operation-1', 'disabled');

    expect(state.pending).toBe(true);
    expect(state.tools[0]?.activationStatus).toBe('enabled');

    state.finishSave({ connector_id: 'connector-1', tools: [{ tool_id: 'operation-1', activation_status: 'enabled', invocation_mode: 'direct', policy_revision: 0 }] });

    expect(state.pending).toBe(false);
    expect(state.dirty).toBe(false);
  });

  test('preserves drafts after a failed or mismatched save', () => {
    const state = new OpenApiOperationCatalogState([createTool(1)]);
    state.setToolActivation('operation-1', 'enabled');

    state.beginSave();
    expect(state.finishSave()).toBeUndefined();

    expect(state.pending).toBe(false);
    expect(state.dirty).toBe(true);
    expect(state.tools[0]?.activationStatus).toBe('enabled');

    state.beginSave();
    expect(state.finishSave({ connector_id: 'connector-1', tools: [] })).toBeUndefined();
    expect(state.dirty).toBe(true);
  });

  test('rejects duplicate, extra, and status-mismatched save acknowledgements', () => {
    const state = new OpenApiOperationCatalogState([createTool(1)]);
    state.setToolActivation('operation-1', 'enabled');

    for (const tools of [
      [
        { tool_id: 'operation-1', activation_status: 'enabled' as const, invocation_mode: 'direct' as const, policy_revision: 0 },
        { tool_id: 'operation-1', activation_status: 'enabled' as const, invocation_mode: 'direct' as const, policy_revision: 0 }
      ],
      [{ tool_id: 'other-operation', activation_status: 'enabled' as const, invocation_mode: 'direct' as const, policy_revision: 0 }],
      [{ tool_id: 'operation-1', activation_status: 'disabled' as const, invocation_mode: 'direct' as const, policy_revision: 0 }]
    ]) {
      state.beginSave();
      expect(state.finishSave({ connector_id: 'connector-1', tools })).toBeUndefined();
      expect(state.dirty).toBe(true);
    }
  });

  test('reconciles partial policy success and authoritative activation failure state', () => {
    const state = new OpenApiOperationCatalogState([createTool(1)], [{ tool_id: 'operation-1', mode: 'direct', revision: 1 }]);
    state.setPolicy('operation-1', 'ask');
    state.setToolActivation('operation-1', 'enabled');

    state.reconcileAuthoritativePolicies([{ tool_id: 'operation-1', mode: 'ask', revision: 2 }]);
    state.reconcileAuthoritativeActivations({ connector_id: 'connector-1', tools: [{ tool_id: 'operation-1', activation_status: 'disabled', invocation_mode: 'ask', policy_revision: 2 }] });

    expect(state.changedPolicies).toEqual([]);
    expect(state.changedTools).toEqual([{ tool_id: 'operation-1', activation_status: 'enabled' }]);
  });

  test('clamps pagination when an activation change reduces filtered results', () => {
    const state = new OpenApiOperationCatalogState(createTools(21));
    state.setStatusFilter('disabled');
    state.nextPage();

    state.setToolActivation('operation-21', 'enabled');

    expect(state.page).toBe(1);
    expect(state.pageCount).toBe(1);
    expect(state.paginatedTools).toHaveLength(20);
  });

  test('returns safe pagination values for an empty catalog and zero matches', () => {
    const emptyState = new OpenApiOperationCatalogState([]);

    expect(emptyState.totalCount).toBe(0);
    expect(emptyState.filteredCount).toBe(0);
    expect(emptyState.pageCount).toBe(1);
    expect(emptyState.page).toBe(1);
    expect(emptyState.paginatedTools).toEqual([]);
    expect(emptyState.canGoPrevious).toBe(false);
    expect(emptyState.canGoNext).toBe(false);
    emptyState.previousPage();
    emptyState.nextPage();
    expect(emptyState.page).toBe(1);

    const zeroMatchState = new OpenApiOperationCatalogState(createTools(3));
    zeroMatchState.setSearch('not-present');

    expect(zeroMatchState.totalCount).toBe(3);
    expect(zeroMatchState.filteredCount).toBe(0);
    expect(zeroMatchState.pageCount).toBe(1);
    expect(zeroMatchState.paginatedTools).toEqual([]);
    expect(zeroMatchState.canGoPrevious).toBe(false);
    expect(zeroMatchState.canGoNext).toBe(false);
  });
});
