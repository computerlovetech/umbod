<script lang="ts">
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import {
    resourceActivationBatchResponseSchema,
    type ResourceCatalog as ResourceCatalogData
  } from '$lib/admin/capability-catalogs';
  import ResourceCatalog from '$lib/components/admin/capability-catalogs/ResourceCatalog.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import { useToast } from '$lib/components/feedback';
  import { DownstreamMcpResourceCatalogState } from './downstream-mcp-resource-catalog-state.svelte';

  let {
    connectorId,
    catalog: initialCatalog,
    onsaved = () => {}
  }: {
    connectorId: string;
    catalog: ResourceCatalogData;
    onsaved?: (connectorId: string, catalog: ResourceCatalogData) => void;
  } = $props();

  const state = new DownstreamMcpResourceCatalogState(untrack(() => initialCatalog));
  const toast = useToast();
</script>

<ResourceCatalog
  embedded
  heading="Resource catalog"
  emptyMessage="No resources are available"
  catalog={state.catalog}
  activationEnabled={state.activationEnabled}
  onActivationChange={state.setResourceActivation}
  dirty={state.dirty}
  pending={state.pending}
>
  <form
    method="POST"
    action="?/saveResourceActivations"
    class="save-form"
    use:enhance={() => {
      const submittedConnectorId = connectorId;
      state.beginSave();
      return async ({ update, result }) => {
        await update({ invalidateAll: false, reset: false });
        if (result.type === 'failure') {
          const resultData = result.data && typeof result.data === 'object' ? result.data : undefined;
          const authoritative = resultData && 'authoritativeResourceResponse' in resultData
            ? resourceActivationBatchResponseSchema.safeParse(resultData.authoritativeResourceResponse)
            : undefined;
          if (authoritative?.success && authoritative.data.connector_id === submittedConnectorId) {
            state.reconcileAuthoritative(authoritative.data);
          }
          state.finishSave();
          toast.error('Could not save resource changes');
          return;
        }
        if (result.type !== 'success') return;
        const candidate = result.data ? resourceActivationBatchResponseSchema.safeParse(result.data.activationResponse) : undefined;
        if (!candidate?.success) throw new Error('Invalid resource activation save result');
        state.finishSave(candidate.data);
        onsaved(submittedConnectorId, state.catalog);
        toast.success('Resource changes saved');
      };
    }}
  >
    <input type="hidden" name="connectorId" value={connectorId} />
    <input type="hidden" name="resourceActivations" value={state.activationRequestJson()} />
    <AdminSaveAction
      label="Save resources"
      loadingLabel="Saving resources..."
      loading={state.pending}
      disabled={!state.dirty || state.pending}
      message={state.pending ? 'Saving resource changes' : state.dirty ? 'Resource changes are not saved' : 'Resource changes saved'}
      tone={state.pending ? 'saving' : state.dirty ? 'warning' : 'success'}
      icon={state.dirty ? '!' : '✓'}
    />
  </form>
</ResourceCatalog>

<style>
  .save-form { align-items: center; display: flex; justify-content: flex-end; margin: 0; }
</style>
