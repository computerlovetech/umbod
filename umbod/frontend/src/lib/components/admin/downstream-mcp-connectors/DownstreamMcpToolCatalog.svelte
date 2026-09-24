<script lang="ts">
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import { downstreamMcpToolActivationBatchResponseSchema, type DownstreamMcpTool } from '$lib/admin/downstream-mcp-connectors';
  import { mapJsonSchemaToConnectorToolParameters } from '$lib/admin/json-schema-tool-parameters';
  import { normalizeNullableToolOutputSchema } from '$lib/admin/tool-output-schema';
  import ToolCard from '$lib/components/admin/connectors/ToolCard.svelte';
  import ToolSaveBar from '$lib/components/admin/connectors/ToolSaveBar.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';
  import ScrollableToolCatalog from '$lib/components/admin/shared/ScrollableToolCatalog.svelte';
  import CatalogControls from '$lib/components/admin/shared/CatalogControls.svelte';
  import CatalogPagination from '$lib/components/admin/shared/CatalogPagination.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import type { SelectOption } from '$lib/components/admin/shared/select-state.svelte';
  import { useToast } from '$lib/components/feedback';
  import DownstreamMcpToolActivationToggle from './DownstreamMcpToolActivationToggle.svelte';
  import InvocationPolicyControl from '$lib/components/admin/connectors/InvocationPolicyControl.svelte';
  import { invocationPolicyListResponseSchema, invocationPolicyConflictSchema, type InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import { DownstreamMcpToolCatalogState, downstreamMcpToolPageSizes, downstreamMcpToolStatusFilters, type DownstreamMcpToolPageSize, type DownstreamMcpToolStatusFilter } from './downstream-mcp-tool-catalog-state.svelte';

  let { connectorId, tools, policies = [], onsaved = () => {} }: { connectorId: string; tools: DownstreamMcpTool[]; policies?: InvocationPolicyTool[]; onsaved?: (connectorId: string, tools: DownstreamMcpTool[]) => void } = $props();
  const catalog = new DownstreamMcpToolCatalogState(untrack(() => tools), untrack(() => policies));
  const toast = useToast();
  const statusOptions: SelectOption[] = [{ value: 'all', label: 'All statuses' }, { value: 'enabled', label: 'Enabled' }, { value: 'disabled', label: 'Disabled' }];
  const pageSizeOptions: SelectOption[] = downstreamMcpToolPageSizes.map((pageSize) => ({ value: String(pageSize), label: String(pageSize) }));
  const countText = $derived(`Showing ${catalog.filteredCount} of ${catalog.totalCount} tools`);
  function isStatusFilter(value: string): value is DownstreamMcpToolStatusFilter { return downstreamMcpToolStatusFilters.some((filter) => filter === value); }
  function setStatusFilter(value: string): void { if (isStatusFilter(value)) catalog.setStatusFilter(value); }
  function isPageSize(value: number): value is DownstreamMcpToolPageSize { return downstreamMcpToolPageSizes.some((size) => size === value); }
  function setPageSize(value: string): void { const size = Number(value); if (isPageSize(size)) catalog.setPageSize(size); }
</script>

<div class="catalog">
  <ToolSaveBar message={catalog.pending ? 'Saving tool changes' : catalog.dirty ? 'Unsaved tool changes' : 'All tool changes saved'} dirty={catalog.dirty} pending={catalog.pending}>
    <form method="POST" action="?/saveToolActivations" class="save-tools" use:enhance={() => {
      const submittedConnectorId = connectorId;
      catalog.beginSave();
      return async ({ update, result }) => {
        await update({ invalidateAll: false, reset: false });
        if (result.type === 'failure') {
          const resultData = result.data && typeof result.data === 'object' ? result.data : undefined;
          const conflicts = resultData && 'policyConflicts' in resultData ? invocationPolicyConflictSchema.array().safeParse(resultData.policyConflicts) : undefined;
          const authoritativePolicies = resultData && 'authoritativePolicyResponse' in resultData ? invocationPolicyListResponseSchema.safeParse(resultData.authoritativePolicyResponse) : undefined;
          const authoritativeActivations = resultData && 'authoritativeActivationResponse' in resultData ? downstreamMcpToolActivationBatchResponseSchema.safeParse(resultData.authoritativeActivationResponse) : undefined;
          if (authoritativePolicies?.success) catalog.reconcileAuthoritativePolicies(authoritativePolicies.data.tools);
          if (authoritativeActivations?.success && authoritativeActivations.data.connector_id === submittedConnectorId) catalog.reconcileAuthoritativeActivations(authoritativeActivations.data);
          if (conflicts?.success) catalog.reconcilePolicies(conflicts.data.map((conflict) => ({ tool_id: conflict.tool_id, mode: conflict.current_mode, revision: conflict.current_revision })), true);
          catalog.finishSave();
          toast.error(conflicts?.success ? 'Policies changed by another administrator. Review and save again.' : 'Could not save tool changes');
          return;
        }
        if (result.type !== 'success') return;
        const candidate = result.data ? downstreamMcpToolActivationBatchResponseSchema.safeParse(result.data.activationResponse) : undefined;
        if (!candidate?.success) throw new Error('Invalid tool activation save result');
        const policyCandidate = result.data ? invocationPolicyListResponseSchema.safeParse(result.data.policyResponse) : undefined;
        if (result.data?.policyResponse !== undefined && !policyCandidate?.success) throw new Error('Invalid invocation policy save result');
        catalog.finishSave(candidate.data);
        if (policyCandidate?.success) catalog.reconcilePolicies(policyCandidate.data.tools);
        onsaved(submittedConnectorId, catalog.tools);
        toast.success('Tool changes saved');
      };
    }}>
      <input type="hidden" name="connectorId" value={connectorId} />
      <input type="hidden" name="toolActivations" value={catalog.activationRequestJson()} />
      <input type="hidden" name="invocationPolicies" value={catalog.policyRequestJson()} />
      <AdminSaveAction label="Save tools" loadingLabel="Saving tools..." loading={catalog.pending} disabled={!catalog.dirty || catalog.pending} message={catalog.pending ? 'Saving tool changes' : catalog.dirty ? 'Tool changes are not saved' : 'Tool changes saved'} tone={catalog.pending ? 'saving' : catalog.dirty ? 'warning' : 'success'} icon={catalog.dirty ? '!' : '✓'} />
    </form>
  </ToolSaveBar>
  <CatalogControls ariaLabel="Tool catalog controls" searchLabel="Search tools" searchPlaceholder="Search by tool name, title, or description" searchValue={catalog.search} onSearchChange={catalog.setSearch} {statusOptions} statusValue={catalog.statusFilter} onStatusChange={setStatusFilter} {pageSizeOptions} pageSizeValue={String(catalog.pageSize)} onPageSizeChange={setPageSize} pageSizeLabel="Tools per page" {countText} />
  {#if catalog.tools.length === 0}<p class="empty">No tools have been discovered. Run discovery to inspect downstream tools.</p>
  {:else if catalog.filteredTools.length === 0}<p class="empty">No tools match your search or filters.</p>
  {:else}
    <ScrollableToolCatalog>
    <CapabilityCatalogGrid>
      {#each catalog.paginatedTools as tool (tool.name)}
        <li>
          <ToolCard title={tool.title} name={tool.name} description={tool.description} parameters={mapJsonSchemaToConnectorToolParameters(tool.input_schema)} outputSchema={normalizeNullableToolOutputSchema(tool.output_schema)}>
            {#snippet controls()}<DownstreamMcpToolActivationToggle {tool} disabled={catalog.pending} onActivationChange={catalog.setToolActivation} /><InvocationPolicyControl toolId={tool.name} mode={catalog.policyMode(tool.name)} disabled={catalog.pending || !catalog.policies[tool.name]} conflict={catalog.conflicts[tool.name] ?? false} onchange={catalog.setPolicy} />{/snippet}
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
  .empty { margin: 0; }
</style>
