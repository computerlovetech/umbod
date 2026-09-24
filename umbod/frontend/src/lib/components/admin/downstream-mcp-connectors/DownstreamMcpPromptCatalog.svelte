<script lang="ts">
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import {
    promptActivationBatchResponseSchema,
    type PromptCatalog as PromptCatalogData
  } from '$lib/admin/capability-catalogs';
  import PromptCatalog from '$lib/components/admin/capability-catalogs/PromptCatalog.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import { useToast } from '$lib/components/feedback';
  import { DownstreamMcpPromptCatalogState } from './downstream-mcp-prompt-catalog-state.svelte';

  let {
    connectorId,
    catalog: initialCatalog,
    onsaved = () => {}
  }: {
    connectorId: string;
    catalog: PromptCatalogData;
    onsaved?: (connectorId: string, catalog: PromptCatalogData) => void;
  } = $props();

  const state = new DownstreamMcpPromptCatalogState(untrack(() => initialCatalog));
  const toast = useToast();
</script>

<PromptCatalog
  embedded
  heading="Prompt catalog"
  emptyMessage="No prompts are available"
  catalog={state.catalog}
  activationEnabled={state.activationEnabled}
  onActivationChange={state.setPromptActivation}
  dirty={state.dirty}
  pending={state.pending}
>
  <form
    method="POST"
    action="?/savePromptActivations"
    class="save-form"
    use:enhance={() => {
      const submittedConnectorId = connectorId;
      state.beginSave();
      return async ({ update, result }) => {
        await update({ invalidateAll: false, reset: false });
        if (result.type === 'failure') {
          const resultData = result.data && typeof result.data === 'object' ? result.data : undefined;
          const authoritative = resultData && 'authoritativePromptResponse' in resultData
            ? promptActivationBatchResponseSchema.safeParse(resultData.authoritativePromptResponse)
            : undefined;
          if (authoritative?.success && authoritative.data.connector_id === submittedConnectorId) {
            state.reconcileAuthoritative(authoritative.data);
          }
          state.finishSave();
          toast.error('Could not save prompt changes');
          return;
        }
        if (result.type !== 'success') return;
        const candidate = result.data ? promptActivationBatchResponseSchema.safeParse(result.data.activationResponse) : undefined;
        if (!candidate?.success) throw new Error('Invalid prompt activation save result');
        state.finishSave(candidate.data);
        onsaved(submittedConnectorId, state.catalog);
        toast.success('Prompt changes saved');
      };
    }}
  >
    <input type="hidden" name="connectorId" value={connectorId} />
    <input type="hidden" name="promptActivations" value={state.activationRequestJson()} />
    <AdminSaveAction
      label="Save prompts"
      loadingLabel="Saving prompts..."
      loading={state.pending}
      disabled={!state.dirty || state.pending}
      message={state.pending ? 'Saving prompt changes' : state.dirty ? 'Prompt changes are not saved' : 'Prompt changes saved'}
      tone={state.pending ? 'saving' : state.dirty ? 'warning' : 'success'}
      icon={state.dirty ? '!' : '✓'}
    />
  </form>
</PromptCatalog>

<style>
  .save-form { align-items: center; display: flex; justify-content: flex-end; margin: 0; }
</style>
