<script lang="ts">
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import { openApiToolActivationBatchResponseSchema, type OpenApiOperationToolUiModel } from '$lib/admin/openapi-connectors';
  import ToolCard from '$lib/components/admin/connectors/ToolCard.svelte';
  import ToolSaveBar from '$lib/components/admin/connectors/ToolSaveBar.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';
  import ScrollableToolCatalog from '$lib/components/admin/shared/ScrollableToolCatalog.svelte';
  import CatalogControls from '$lib/components/admin/shared/CatalogControls.svelte';
  import CatalogPagination from '$lib/components/admin/shared/CatalogPagination.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';
  import OpenApiToolActivationToggle from './OpenApiToolActivationToggle.svelte';
  import InvocationPolicyControl from '$lib/components/admin/connectors/InvocationPolicyControl.svelte';
  import { invocationPolicyConflictSchema, invocationPolicyListResponseSchema, type InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import { OpenApiOperationCatalogState, openApiOperationPageSizes, openApiOperationStatusFilters, type OpenApiOperationPageSize, type OpenApiOperationStatusFilter } from './openapi-operation-catalog-state.svelte';

  let { connectorId, tools, policies = [], onsaved = () => {} }: { connectorId: string; tools: OpenApiOperationToolUiModel[]; policies?: InvocationPolicyTool[]; onsaved?: (connectorId: string, tools: OpenApiOperationToolUiModel[]) => void; } = $props();
  const catalog = new OpenApiOperationCatalogState(untrack(() => tools), untrack(() => policies));
  function isStatusFilter(value: string): value is OpenApiOperationStatusFilter { return openApiOperationStatusFilters.some((statusFilter) => statusFilter === value); }
  function handleStatusFilterChange(value: string): void { if (isStatusFilter(value)) catalog.setStatusFilter(value); }
  function isPageSize(value: number): value is OpenApiOperationPageSize { return openApiOperationPageSizes.some((pageSize) => pageSize === value); }
  function handlePageSizeChange(value: string): void { const pageSize = Number(value); if (isPageSize(pageSize)) catalog.setPageSize(pageSize); }
  const statusOptions: SelectOption[] = [{ value: 'all', label: 'All statuses' }, { value: 'enabled', label: 'Enabled' }, { value: 'disabled', label: 'Disabled' }];
  const pageSizeOptions: SelectOption[] = openApiOperationPageSizes.map((pageSize) => ({ value: String(pageSize), label: String(pageSize) }));
  const methodOptions = $derived<SelectOption[]>([{ value: 'all', label: 'All methods' }, ...catalog.availableMethods.map((method) => ({ value: method, label: method }))]);
  const countText = $derived(`Showing ${catalog.filteredCount} of ${catalog.totalCount} tools`);
</script>

<div class="catalog">
  <ToolSaveBar message={catalog.pending ? 'Saving tool changes' : catalog.dirty ? 'Unsaved tool changes' : 'All tool changes saved'} dirty={catalog.dirty} pending={catalog.pending}>
    <form method="POST" action="?/saveToolActivations" class="save-tools" use:enhance={() => {
      const submittedConnectorId = connectorId;
      catalog.beginSave();
      return async ({ update, result }) => {
        await update({ invalidateAll: false, reset: false });
        if (result.type === 'failure' && result.data && typeof result.data === 'object') {
          const conflicts = 'policyConflicts' in result.data ? invocationPolicyConflictSchema.array().safeParse(result.data.policyConflicts) : undefined;
          const authoritativePolicies = 'authoritativePolicyResponse' in result.data ? invocationPolicyListResponseSchema.safeParse(result.data.authoritativePolicyResponse) : undefined;
          const authoritativeActivations = 'authoritativeActivationResponse' in result.data ? openApiToolActivationBatchResponseSchema.safeParse(result.data.authoritativeActivationResponse) : undefined;
          if (authoritativePolicies?.success) catalog.reconcileAuthoritativePolicies(authoritativePolicies.data.tools);
          if (authoritativeActivations?.success && authoritativeActivations.data.connector_id === submittedConnectorId) catalog.reconcileAuthoritativeActivations(authoritativeActivations.data);
          if (conflicts?.success) catalog.reconcilePolicies(conflicts.data.map((conflict) => ({ tool_id: conflict.tool_id, mode: conflict.current_mode, revision: conflict.current_revision })), true);
        }
        const candidate = result.type === 'success' && result.data ? openApiToolActivationBatchResponseSchema.safeParse(result.data.activationResponse) : undefined;
        const policyCandidate = result.type === 'success' && result.data ? invocationPolicyListResponseSchema.safeParse(result.data.policyResponse) : undefined;
        if (result.type === 'success' && result.data?.policyResponse !== undefined && !policyCandidate?.success) throw new Error('Invalid invocation policy save result');
        if (policyCandidate?.success) catalog.reconcilePolicies(policyCandidate.data.tools);
        const response = candidate?.success && candidate.data.connector_id === submittedConnectorId ? candidate.data : undefined;
        const savedTools = catalog.finishSave(response);
        if (savedTools) onsaved(submittedConnectorId, savedTools);
      };
    }}>
      <input type="hidden" name="connectorId" value={connectorId} />
      <input type="hidden" name="toolActivations" value={catalog.activationRequestJson()} />
      <input type="hidden" name="invocationPolicies" value={catalog.policyRequestJson()} />
      <AdminSaveAction label="Save tools" loadingLabel="Saving tools..." loading={catalog.pending} disabled={!catalog.dirty || catalog.pending} message={catalog.pending ? 'Saving tool changes' : catalog.dirty ? 'Tool changes are not saved' : 'Tool changes saved'} tone={catalog.pending ? 'saving' : catalog.dirty ? 'warning' : 'success'} icon={catalog.dirty ? '!' : '✓'} />
    </form>
  </ToolSaveBar>
  <CatalogControls ariaLabel="Tool catalog controls" searchLabel="Search tools" searchPlaceholder="Search by tool name, method, path, summary, or description" searchValue={catalog.search} onSearchChange={catalog.setSearch} {methodOptions} methodValue={catalog.methodFilter} onMethodChange={catalog.setMethodFilter} {statusOptions} statusValue={catalog.statusFilter} onStatusChange={handleStatusFilterChange} {pageSizeOptions} pageSizeValue={String(catalog.pageSize)} onPageSizeChange={handlePageSizeChange} pageSizeLabel="Tools per page" {countText} />
  {#if catalog.tools.length === 0}<p class="empty">No tools have been imported for this connector.</p>
  {:else if catalog.filteredTools.length === 0}<p class="empty">No tools match your search or filters.</p>
  {:else}
    <ScrollableToolCatalog>
    <CapabilityCatalogGrid>
      {#each catalog.paginatedTools as tool (tool.operationId)}
        <li>
          <ToolCard title={tool.summary || tool.operationId} name={tool.operationId} description={`${tool.method.toUpperCase()} ${tool.path}${tool.description ? ` · ${tool.description}` : ''}`} parameters={tool.parameters ?? []} outputSchema={tool.outputSchema}>
            {#snippet controls()}<OpenApiToolActivationToggle operationId={tool.operationId} activationStatus={tool.activationStatus} disabled={catalog.pending} onActivationChange={catalog.setToolActivation} /><InvocationPolicyControl toolId={tool.operationId} mode={catalog.policyMode(tool.operationId)} disabled={catalog.pending || !catalog.policies[tool.operationId]} conflict={catalog.conflicts[tool.operationId] ?? false} onchange={catalog.setPolicy} />{/snippet}
          </ToolCard>
        </li>
      {/each}
    </CapabilityCatalogGrid>
    </ScrollableToolCatalog>
    <CatalogPagination ariaLabel="Tool catalog pagination" page={catalog.page} pageCount={catalog.pageCount} canGoPrevious={catalog.canGoPrevious} canGoNext={catalog.canGoNext} onPrevious={catalog.previousPage} onNext={catalog.nextPage} />
  {/if}
</div>

<style>
  .catalog { color: #37352f; }
  .save-tools { align-items: center; display: flex; justify-content: flex-end; margin: 0; }
  .empty { color: #787774; font-size: 0.875rem; line-height: 1.55; margin: 0.7rem 0 0; }
</style>
