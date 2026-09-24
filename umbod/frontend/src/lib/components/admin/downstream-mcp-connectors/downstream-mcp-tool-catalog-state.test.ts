import type { DownstreamMcpTool } from '$lib/admin/downstream-mcp-connectors';
import { describe, expect, test } from 'vitest';
import { DownstreamMcpToolCatalogState } from './downstream-mcp-tool-catalog-state.svelte';

function createTool(index: number, overrides: Partial<DownstreamMcpTool> = {}): DownstreamMcpTool {
  return { name: `tool-${index}`, title: `Tool ${index}`, description: `Description ${index}`, input_schema: {}, output_schema: null, activation_status: 'disabled', ...overrides };
}
function createTools(count: number): DownstreamMcpTool[] { return Array.from({ length: count }, (_, index) => createTool(index + 1)); }

describe('DownstreamMcpToolCatalogState', () => {
  test.each([
    ['name', { name: 'InvoiceLookup' }, 'InvoiceLookup'],
    ['title', { title: 'Invoice lookup' }, 'tool-1'],
    ['description', { description: 'Looks up invoices' }, 'tool-1']
  ])('searches case-insensitively across %s', (_, overrides, expectedName) => {
    const state = new DownstreamMcpToolCatalogState([createTool(1, overrides), createTool(2)]);
    state.setSearch('INVOICE');
    expect(state.filteredTools.map((tool) => tool.name)).toEqual([expectedName]);
  });

  test('filters activation status and reports total and filtered counts', () => {
    const state = new DownstreamMcpToolCatalogState([createTool(1, { activation_status: 'enabled' }), createTool(2)]);
    state.setStatusFilter('enabled');
    expect(state.totalCount).toBe(2);
    expect(state.filteredCount).toBe(1);
    expect(state.filteredTools[0]?.name).toBe('tool-1');
  });

  test('paginates at each supported size and resets after filter changes', () => {
    const state = new DownstreamMcpToolCatalogState(createTools(125));
    state.nextPage();
    expect(state.page).toBe(2);
    state.setSearch('tool');
    expect(state.page).toBe(1);
    state.nextPage();
    state.setStatusFilter('disabled');
    expect(state.page).toBe(1);
    state.nextPage();
    state.setPageSize(50);
    expect(state.page).toBe(1);
    expect(state.paginatedTools).toHaveLength(50);
    state.setPageSize(100);
    expect(state.paginatedTools).toHaveLength(100);
  });

  test.each([
    ['enabled', 'disabled'],
    ['disabled', 'enabled']
  ] as const)('updates a tool to %s immutably while preserving view state', (activationStatus, initialStatus) => {
    const originalTools = [createTool(1, { activation_status: initialStatus }), createTool(2)];
    const state = new DownstreamMcpToolCatalogState(originalTools);
    state.setSearch('tool');
    state.setStatusFilter('all');
    state.setPageSize(50);

    state.setToolActivation('tool-1', activationStatus);

    expect(state.tools).not.toBe(originalTools);
    expect(state.tools[0]).not.toBe(originalTools[0]);
    expect(state.tools[0]?.activation_status).toBe(activationStatus);
    expect(state.tools[1]).toBe(originalTools[1]);
    expect(state.search).toBe('tool');
    expect(state.statusFilter).toBe('all');
    expect(state.pageSize).toBe(50);
    expect(state.page).toBe(1);
  });

  test('retains a dirty draft after failure and promotes it only after success', () => {
    const state = new DownstreamMcpToolCatalogState([createTool(1)]);
    state.setToolActivation('tool-1', 'enabled');
    expect(state.dirty).toBe(true);
    expect(JSON.parse(state.activationRequestJson())).toEqual({ tools: [{ tool_id: 'tool-1', activation_status: 'enabled' }] });
    state.beginSave();
    state.setToolActivation('tool-1', 'disabled');
    expect(state.tools[0]?.activation_status).toBe('enabled');
    state.finishSave();
    expect(state.dirty).toBe(true);
    state.beginSave();
    state.finishSave({ connector_id: 'connector', tools: [{ tool_id: 'tool-1', activation_status: 'enabled', invocation_mode: 'direct', policy_revision: 0 }] });
    expect(state.dirty).toBe(false);
  });

  test('reconciles partial policy success and authoritative activation failure state', () => {
    const state = new DownstreamMcpToolCatalogState([createTool(1)], [{ tool_id: 'tool-1', mode: 'direct', revision: 1 }]);
    state.setPolicy('tool-1', 'ask');
    state.setToolActivation('tool-1', 'enabled');

    state.reconcileAuthoritativePolicies([{ tool_id: 'tool-1', mode: 'ask', revision: 2 }]);
    state.reconcileAuthoritativeActivations({ connector_id: 'connector', tools: [{ tool_id: 'tool-1', activation_status: 'disabled', invocation_mode: 'ask', policy_revision: 2 }] });

    expect(state.changedPolicies).toEqual([]);
    expect(state.changedTools).toEqual([{ tool_id: 'tool-1', activation_status: 'enabled' }]);
  });

  test('provides safe empty and no-match states', () => {
    const empty = new DownstreamMcpToolCatalogState([]);
    expect(empty.totalCount).toBe(0);
    expect(empty.filteredCount).toBe(0);
    expect(empty.pageCount).toBe(1);
    expect(empty.paginatedTools).toEqual([]);
    const noMatch = new DownstreamMcpToolCatalogState(createTools(2));
    noMatch.setSearch('absent');
    expect(noMatch.totalCount).toBe(2);
    expect(noMatch.filteredCount).toBe(0);
    expect(noMatch.pageCount).toBe(1);
    expect(noMatch.canGoNext).toBe(false);
  });
});
