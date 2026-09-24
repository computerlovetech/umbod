<script lang="ts">
  import { enhance } from '$app/forms';
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import { promptActivationBatchResponseSchema, resourceActivationBatchResponseSchema } from '$lib/admin/capability-catalogs';
  import { connectorToolActivationBatchResponseSchema, type ConnectorListItem } from '$lib/admin/connectors';
  import PromptCatalog from '$lib/components/admin/capability-catalogs/PromptCatalog.svelte';
  import ResourceCatalog from '$lib/components/admin/capability-catalogs/ResourceCatalog.svelte';
  import { ConnectorDetailsBrowserRoute, type ConnectorDetailBundle } from '$lib/admin/connector-details-browser-api';
  import CapabilityDescriptionOverrideModal from '$lib/components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte';
  import ConnectorCapabilities from '$lib/components/admin/connectors/ConnectorCapabilities.svelte';
  import ConnectorConfigurationForm from '$lib/components/admin/connectors/ConnectorConfigurationForm.svelte';
  import ConnectorDetailItem from '$lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import ConnectorDetailSummary from '$lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorPublicationMenuAction from '$lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte';
  import ConnectorSidebarList from '$lib/components/admin/connectors/ConnectorSidebarList.svelte';
  import PublicationConfirmationModal from '$lib/components/admin/connectors/PublicationConfirmationModal.svelte';
  import ToolCard from '$lib/components/admin/connectors/ToolCard.svelte';
  import InvocationPolicyControl from '$lib/components/admin/connectors/InvocationPolicyControl.svelte';
  import { invocationPolicyConflictSchema, invocationPolicyListResponseSchema } from '$lib/admin/invocation-policy';
  import ToolSaveBar from '$lib/components/admin/connectors/ToolSaveBar.svelte';
  import CapabilityCatalogGrid from '$lib/components/admin/shared/CapabilityCatalogGrid.svelte';
  import ScrollableToolCatalog from '$lib/components/admin/shared/ScrollableToolCatalog.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import AdminToggle from '$lib/components/admin/shared/AdminToggle.svelte';
  import AdminSaveAction from '$lib/components/admin/shared/AdminSaveAction.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import LoadingButton from '$lib/components/admin/shared/LoadingButton.svelte';
  import { FormPendingState } from '$lib/components/admin/shared/form-pending-state.svelte';
  import { BrowserSelectionUrlAdapter } from '$lib/components/admin/shared/selection-url-port';
  import { ConnectorListState } from './connector-list-state.svelte';
  import { useToast } from '$lib/components/feedback';

  type ConnectorListForm = {
    status?: string;
    connectorId?: string;
    errorMessage?: string;
  };

  type SaveFeedback = {
    message: string;
    tone: 'success' | 'warning' | 'error' | 'muted' | 'saving';
    icon: string;
  };

  let {
    connectors,
    form,
    onconfigure,
    selectedConnectorId,
    initialDetail,
    initialDetailFailed
  }: {
    connectors: ConnectorListItem[];
    form?: ConnectorListForm;
    onconfigure: (connectorId: string) => void;
    selectedConnectorId?: string;
    initialDetail?: ConnectorDetailBundle;
    initialDetailFailed?: boolean;
  } = $props();

  const detailsRoute = new ConnectorDetailsBrowserRoute();
  const state = new ConnectorListState(untrack(() => connectors), {
    selectedConnectorId: untrack(() => selectedConnectorId),
    initialDetail: untrack(() => initialDetail),
    initialDetailFailed: untrack(() => initialDetailFailed),
    loadDetail: (connectorId, signal) => detailsRoute.get(connectorId, signal),
    selectionUrl: new BrowserSelectionUrlAdapter({ readUrl: () => page.url, replaceUrl: (url) => replaceState(url, {}) })
  });
  const pendingState = new FormPendingState();
  const toast = useToast();
  const selectedCapability = $derived(parseConnectorCapability(page.url.searchParams.get('capability')));
  const capabilityCounts = $derived({
    tools: state.selectedConnector?.tools.length ?? 0,
    prompts: state.selectedPromptCatalog.prompts.length,
    resources: state.selectedResourceCatalog.resources.length
  });

  function inputChecked(event: Event): boolean {
    return event.currentTarget instanceof HTMLInputElement ? event.currentTarget.checked : false;
  }

  function saveToolsPendingKey(connectorId: string | null): string {
    return `save-tools:${connectorId ?? ''}`;
  }

  function savePromptsPendingKey(connectorId: string | null): string {
    return `save-prompts:${connectorId ?? ''}`;
  }

  function saveResourcesPendingKey(connectorId: string | null): string {
    return `save-resources:${connectorId ?? ''}`;
  }

  function saveToolsFeedback(connectorId: string | null): SaveFeedback {
    if (pendingState.isPending(saveToolsPendingKey(connectorId))) {
      return { message: 'Saving tool changes…', tone: 'saving', icon: '' };
    }

    if (state.hasUnsavedToolChanges) {
      return { message: 'Unsaved tool changes', tone: 'warning', icon: '•' };
    }

    return { message: 'All tool changes saved', tone: 'muted', icon: '✓' };
  }

  function savePromptsFeedback(connectorId: string | null): SaveFeedback {
    if (pendingState.isPending(savePromptsPendingKey(connectorId))) {
      return { message: 'Saving prompt changes…', tone: 'saving', icon: '' };
    }
    if (state.hasUnsavedPromptChanges) {
      return { message: 'Unsaved prompt changes', tone: 'warning', icon: '•' };
    }
    return { message: 'All prompt changes saved', tone: 'muted', icon: '✓' };
  }

  function saveResourcesFeedback(connectorId: string | null): SaveFeedback {
    if (pendingState.isPending(saveResourcesPendingKey(connectorId))) {
      return { message: 'Saving resource changes…', tone: 'saving', icon: '' };
    }
    if (state.hasUnsavedResourceChanges) {
      return { message: 'Unsaved resource changes', tone: 'warning', icon: '•' };
    }
    return { message: 'All resource changes saved', tone: 'muted', icon: '✓' };
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  type SaveToolsActionData =
    | { status: 'saved'; connectorId: string }
    | { status: 'failed'; connectorId: string; errorMessage: string };

  function saveToolsDataFromActionResult(result: unknown): SaveToolsActionData {
    if (!isRecord(result) || !isRecord(result.data) || typeof result.data.connectorId !== 'string') {
      throw new Error('Invalid save tool activations result');
    }

    if (result.data.status === 'saved') return { status: 'saved', connectorId: result.data.connectorId };
    if (result.data.status === 'failed' && typeof result.data.errorMessage === 'string') {
      return { status: 'failed', connectorId: result.data.connectorId, errorMessage: result.data.errorMessage };
    }
    throw new Error('Invalid save tool activations result');
  }

  function requestPublicationConfirmation(event: MouseEvent, connectorName: string, actionLabel: 'Publish' | 'Unpublish'): void {
    if (!(event.currentTarget instanceof HTMLButtonElement) || !event.currentTarget.form) {
      return;
    }

    state.requestPublicationConfirmation(event.currentTarget.form, connectorName, actionLabel);
  }
</script>

{#if state.capabilityDescriptionConnectorId}
  <CapabilityDescriptionOverrideModal kind="native" connectorId={state.capabilityDescriptionConnectorId} close={state.closeCapabilityDescription} />
{/if}

<PublicationConfirmationModal
  open={Boolean(state.pendingPublication)}
  title={state.modalTitle}
  message={state.modalMessage}
  confirmLabel={state.pendingPublication?.actionLabel ?? 'Confirm'}
  onconfirm={state.confirmPublication}
  oncancel={state.cancelPublication}
/>

{#if connectors.length > 0 && state.selectedConnector}
  <AdminSplitWorkspace
    ariaLabel="Connectors workspace"
    sidebarLabel="Connectors"
    sidebarHeading="Connectors"
    count={connectors.length}
    detailLabel="Selected connector detail"
  >
    {#snippet sidebar()}
      <ConnectorSidebarList items={connectors} selectedId={state.selectedConnector.id} ariaLabel="Connectors" onselect={(connector) => state.selectConnector(connector.id)}>
        {#snippet metadata(connector)}
          <span class="connector-meta">{connector.id}</span>
          <span class="connector-meta">{connector.sourceLabel} · {connector.publicationStatus}</span>
        {/snippet}
        {#snippet actions(connector)}
          <AdminSidebarActionMenu open={state.openMenuConnectorId === connector.id} label={`Open actions for ${connector.name}`} onopenchange={(open) => state.setMenuOpen(connector.id, open)}>
            {#snippet menu()}
              <button type="button" role="menuitem" onclick={() => { state.closeMenu(); onconfigure(connector.id); }}>Configure</button>
              <button type="button" role="menuitem" onclick={() => state.showCapabilityDescription(connector.id)}>Edit capability description</button>
              {#if connector.canPublish || connector.canUnpublish}
                <ConnectorPublicationMenuAction connectorId={connector.id} connectorName={connector.name} action={connector.canPublish ? 'publish' : 'unpublish'} onrequest={requestPublicationConfirmation} />
              {/if}
            {/snippet}
          </AdminSidebarActionMenu>
        {/snippet}
      </ConnectorSidebarList>
    {/snippet}

    {#snippet detail()}
      {#if state.detailLoading}
        <div class="admin-message"><DelayedSpinner active label="Loading connector details" /></div>
      {:else if state.detailFailed}
        <div class="admin-message admin-message-error" role="alert"><p>Connector details are unavailable.</p><Button onclick={state.retryDetail}>Try again</Button></div>
      {:else}
      <ConnectorDetailSummary headingId="selected-connector-heading" title={state.selectedConnector.name} iconDataUrl={state.selectedConnector.iconDataUrl} publicationStatus={state.selectedConnector.publicationStatus}>
        {#snippet description()}
          <p class="description">{state.selectedConnector.description}</p>
        {/snippet}
        {#snippet summary()}
          <ConnectorDetailItem label="Source" tone="neutral">{state.selectedConnector.sourceLabel}</ConnectorDetailItem>
          <ConnectorDetailItem label="Tools" tone="neutral">{state.selectedConnector.tools.length} tools</ConnectorDetailItem>
        {/snippet}
        {#snippet technicalDetails()}
          <ConnectorDetailItem label="Connector ID" variant="detail"><code>{state.selectedConnector.id}</code></ConnectorDetailItem>
          <ConnectorDetailItem label="Publication status" variant="detail">{state.selectedConnector.publicationStatus}</ConnectorDetailItem>
        {/snippet}

        <ConnectorCapabilities selected={selectedCapability} counts={capabilityCounts} currentUrl={page.url}>
        {#snippet children(activeCapability)}
        {#if activeCapability === 'tools'}
          <section class="tools-section" aria-labelledby="connector-tools-heading">
            <h3 id="connector-tools-heading">Tools exposed to agent users</h3>
            {#if state.selectedConnector.tools.length === 0}
              <p class="empty-note compact">This connector does not expose any tools.</p>
            {:else}
              {@const currentSaveToolsFeedback = saveToolsFeedback(state.selectedConnector.id)}
              {@const saveToolsPending = pendingState.isPending(saveToolsPendingKey(state.selectedConnector.id))}
              <ToolSaveBar
                message={saveToolsPending ? 'Saving tool changes' : state.hasUnsavedToolChanges ? 'Unsaved tool changes' : 'All tool changes saved'}
                dirty={state.hasUnsavedToolChanges}
                pending={saveToolsPending}
              >
                <form
                  method="POST"
                  action="?/saveToolActivations"
                  class="save-tools"
                  use:enhance={() => {
                    const submission = state.captureToolActivationSubmission();
                    const pendingKey = saveToolsPendingKey(submission?.connectorId ?? null);
                    pendingState.start(pendingKey);

                    return async ({ update, result }) => {
                      try {
                        if (result.type === 'failure' && isRecord(result.data)) {
                          const conflicts = 'policyConflicts' in result.data ? invocationPolicyConflictSchema.array().safeParse(result.data.policyConflicts) : undefined;
                          const authoritativePolicies = 'authoritativePolicyResponse' in result.data ? invocationPolicyListResponseSchema.safeParse(result.data.authoritativePolicyResponse) : undefined;
                          const authoritativeActivations = 'authoritativeActivationResponse' in result.data ? connectorToolActivationBatchResponseSchema.safeParse(result.data.authoritativeActivationResponse) : undefined;
                          if (authoritativePolicies?.success) state.reconcileAuthoritativePolicies(authoritativePolicies.data.tools);
                          if (authoritativeActivations?.success && submission?.connectorId === authoritativeActivations.data.connector_id) state.reconcileAuthoritativeActivations(authoritativeActivations.data.connector_id, authoritativeActivations.data.tools);
                          if (conflicts?.success) state.reconcilePolicies(conflicts.data.map((conflict) => ({ tool_id: conflict.tool_id, mode: conflict.current_mode, revision: conflict.current_revision })), true);
                          toast.error(conflicts?.success ? 'Policies changed by another administrator. Review and save again.' : 'Could not save tool changes');
                          await update({ invalidateAll: false, reset: false });
                          return;
                        }
                        const actionData = saveToolsDataFromActionResult(result);
                        if (actionData.status === 'saved') {
                          const resultData = result.type === 'success' && isRecord(result.data) ? result.data : undefined;
                          const policyResponse = resultData ? invocationPolicyListResponseSchema.safeParse(resultData.policyResponse) : undefined;
                          if (resultData?.policyResponse !== undefined && !policyResponse?.success) throw new Error('Invalid invocation policy save result');
                          if (policyResponse?.success) state.reconcilePolicies(policyResponse.data.tools);
                          if (submission?.connectorId === actionData.connectorId) state.markToolActivationsSaved(actionData.connectorId, submission.changes);
                          toast.success('Tool changes saved');
                        } else {
                          toast.error(actionData.errorMessage);
                        }
                        await update();
                      } finally {
                        pendingState.stop(pendingKey);
                      }
                    };
                  }}
                >
                  <input type="hidden" name="connectorId" value={state.selectedConnector.id} />
                  <input type="hidden" name="toolActivations" value={state.selectedToolActivationDraftsJson} />
                  <input type="hidden" name="invocationPolicies" value={state.invocationPoliciesJson} />
                  <AdminSaveAction
                    label="Save tools"
                    loadingLabel="Saving tools..."
                    loading={saveToolsPending}
                    disabled={!state.hasUnsavedToolChanges}
                    message={currentSaveToolsFeedback.message}
                    tone={currentSaveToolsFeedback.tone}
                    icon={currentSaveToolsFeedback.icon}
                  />
                </form>
              </ToolSaveBar>
              <ScrollableToolCatalog>
              <CapabilityCatalogGrid>
                {#each state.selectedConnector.tools as tool (tool.operationName)}
                  <li>
                    <ToolCard title={tool.label} name={tool.operationName} description={tool.description} parameters={tool.parameters} outputSchema={tool.outputSchema}>
                      {#snippet controls()}
                        <AdminToggle
                          checked={state.toolActivationIsEnabled(tool.operationName)}
                          ariaLabel={`${tool.label} activation`}
                          onchange={(event) => state.setToolActivation(tool.operationName, inputChecked(event))}
                        />
                        <InvocationPolicyControl toolId={tool.operationName} mode={state.policyMode(tool.operationName)} disabled={!state.policies[tool.operationName] || saveToolsPending} conflict={state.policyConflicts[tool.operationName] ?? false} onchange={state.setPolicy} />
                      {/snippet}
                    </ToolCard>
                  </li>
                {/each}
              </CapabilityCatalogGrid>
              </ScrollableToolCatalog>
            {/if}
          </section>
        {:else if activeCapability === 'prompts'}
          {@const savePromptsPending = pendingState.isPending(savePromptsPendingKey(state.selectedConnector.id))}
          {@const currentSavePromptsFeedback = savePromptsFeedback(state.selectedConnector.id)}
          <PromptCatalog
            embedded
            catalog={state.selectedPromptCatalog}
            activationEnabled={state.promptActivationIsEnabled}
            onActivationChange={state.setPromptActivation}
            dirty={state.hasUnsavedPromptChanges}
            pending={savePromptsPending}
            saveBarMessage={currentSavePromptsFeedback.message}
          >
            <form
              method="POST"
              action="?/savePromptActivations"
              class="save-tools"
              use:enhance={() => {
                const submission = state.capturePromptActivationSubmission();
                const pendingKey = savePromptsPendingKey(submission?.connectorId ?? null);
                pendingState.start(pendingKey);
                return async ({ update, result }) => {
                  try {
                    if (result.type === 'failure' && isRecord(result.data)) {
                      const authoritative = 'authoritativePromptResponse' in result.data
                        ? promptActivationBatchResponseSchema.safeParse(result.data.authoritativePromptResponse)
                        : undefined;
                      if (authoritative?.success) {
                        state.reconcileAuthoritativePromptActivations(
                          authoritative.data.connector_id,
                          authoritative.data.prompts
                        );
                      }
                      toast.error('Could not save prompt changes');
                      await update({ invalidateAll: false, reset: false });
                      return;
                    }
                    if (result.type === 'success' && isRecord(result.data) && result.data.status === 'saved' && submission) {
                      state.markPromptActivationsSaved(submission.connectorId, submission.changes);
                      toast.success('Prompt changes saved');
                    } else {
                      toast.error('Could not save prompt changes');
                    }
                    await update();
                  } finally {
                    pendingState.stop(pendingKey);
                  }
                };
              }}
            >
              <input type="hidden" name="connectorId" value={state.selectedConnector.id} />
              <input type="hidden" name="promptActivations" value={state.selectedPromptActivationDraftsJson} />
              <AdminSaveAction
                label="Save prompts"
                loadingLabel="Saving prompts..."
                loading={savePromptsPending}
                disabled={!state.hasUnsavedPromptChanges}
                message={currentSavePromptsFeedback.message}
                tone={currentSavePromptsFeedback.tone}
                icon={currentSavePromptsFeedback.icon}
              />
            </form>
          </PromptCatalog>
        {:else}
          {@const saveResourcesPending = pendingState.isPending(saveResourcesPendingKey(state.selectedConnector.id))}
          {@const currentSaveResourcesFeedback = saveResourcesFeedback(state.selectedConnector.id)}
          <ResourceCatalog
            embedded
            catalog={state.selectedResourceCatalog}
            activationEnabled={state.resourceActivationIsEnabled}
            onActivationChange={state.setResourceActivation}
            dirty={state.hasUnsavedResourceChanges}
            pending={saveResourcesPending}
            saveBarMessage={currentSaveResourcesFeedback.message}
          >
            <form
              method="POST"
              action="?/saveResourceActivations"
              class="save-tools"
              use:enhance={() => {
                const submission = state.captureResourceActivationSubmission();
                const pendingKey = saveResourcesPendingKey(submission?.connectorId ?? null);
                pendingState.start(pendingKey);
                return async ({ update, result }) => {
                  try {
                    if (result.type === 'failure' && isRecord(result.data)) {
                      const authoritative = 'authoritativeResourceResponse' in result.data
                        ? resourceActivationBatchResponseSchema.safeParse(result.data.authoritativeResourceResponse)
                        : undefined;
                      if (authoritative?.success) {
                        state.reconcileAuthoritativeResourceActivations(
                          authoritative.data.connector_id,
                          authoritative.data.resources
                        );
                      }
                      toast.error('Could not save resource changes');
                      await update({ invalidateAll: false, reset: false });
                      return;
                    }
                    if (result.type === 'success' && isRecord(result.data) && result.data.status === 'saved' && submission) {
                      state.markResourceActivationsSaved(submission.connectorId, submission.changes);
                      toast.success('Resource changes saved');
                    } else {
                      toast.error('Could not save resource changes');
                    }
                    await update();
                  } finally {
                    pendingState.stop(pendingKey);
                  }
                };
              }}
            >
              <input type="hidden" name="connectorId" value={state.selectedConnector.id} />
              <input type="hidden" name="resourceActivations" value={state.selectedResourceActivationDraftsJson} />
              <AdminSaveAction
                label="Save resources"
                loadingLabel="Saving resources..."
                loading={saveResourcesPending}
                disabled={!state.hasUnsavedResourceChanges}
                message={currentSaveResourcesFeedback.message}
                tone={currentSaveResourcesFeedback.tone}
                icon={currentSaveResourcesFeedback.icon}
              />
            </form>
          </ResourceCatalog>
        {/if}
        {/snippet}
        </ConnectorCapabilities>
        {#if state.visibleAction === 'configuration'}
          <section class="configuration-section" aria-labelledby="connector-configuration-heading">
            <h3 id="connector-configuration-heading">Configure connector</h3>
            {#if state.selectedConnector.configurationFields}
              <ConnectorConfigurationForm
                connector={state.selectedConnector}
                fields={state.selectedConnector.configurationFields}
                action="?/saveConfiguration"
                submitConnectorId={true}
                {form}
              />
            {:else}
              <p class="empty-note compact">This connector configuration could not be loaded.</p>
            {/if}
          </section>
        {/if}
      </ConnectorDetailSummary>
      {/if}
    {/snippet}
  </AdminSplitWorkspace>
{:else}
  <p class="empty-note">No connectors are available yet.</p>
{/if}

<style>
  h3,
  p {
    margin: 0;
  }

  h3 {
    color: #37352f;
    font-size: 0.95rem;
    margin-bottom: 0.75rem;
  }

  .description {
    color: #787774;
    line-height: 1.55;
    margin-top: 1rem;
    max-width: 46rem;
  }

  .tools-section { min-width: 0; }

  .configuration-section {
    border-top: 1px solid #e9e9e7;
    margin-top: 1.5rem;
    padding-top: 1.25rem;
  }

  .save-tools {
    display: flex;
    justify-content: flex-end;
    margin: 0;
  }

  .compact {
    margin-top: 0;
  }

  .empty-note {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 10px;
    color: #787774;
    margin: 1.5rem 0 0;
    padding: 1rem;
  }

</style>
