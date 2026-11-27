<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { useToast } from '#lib/components/feedback/index.js';
  import { onMount, untrack } from 'svelte';
  import { parseConnectorCapability } from '#lib/admin/connector-capabilities.js';
  import { OpenApiConnectorToolsBrowserRoute } from '#lib/admin/openapi-connector-tools-browser-api.js';
  import { OpenApiConnectorDetailsBrowserRoute } from '#lib/admin/openapi-connector-details-browser-api.js';
  import type { OpenApiConnectorListItem, OpenApiConnectorListPageData, OpenApiToolActivationStatus } from '#lib/admin/openapi-connectors.js';
  import type { InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
  import { emptyPromptCatalog, emptyResourceCatalog } from '#lib/admin/capability-catalogs.js';
  import PromptCatalog from '#lib/components/admin/capability-catalogs/PromptCatalog.svelte';
  import ResourceCatalog from '#lib/components/admin/capability-catalogs/ResourceCatalog.svelte';
  import CapabilityDescriptionOverrideModal from '#lib/components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte';
  import ConnectorCapabilities from '#lib/components/admin/connectors/ConnectorCapabilities.svelte';
  import ConnectorDetailItem from '#lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import ConnectorStatusOverview from '#lib/components/admin/connectors/ConnectorStatusOverview.svelte';
  import ConnectorDetailSummary from '#lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorReferenceGroup from '#lib/components/admin/connectors/ConnectorReferenceGroup.svelte';
  import CopyableValue from '#lib/components/admin/connectors/CopyableValue.svelte';
  import ConnectorPublicationMenuAction from '#lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte';
  import UnifiedConnectorWorkspace from '#lib/components/admin/connectors/UnifiedConnectorWorkspace.svelte';
  import type { UnifiedConnectorKind, UnifiedConnectorRow } from '#lib/admin/unified-connectors.js';
  import PublicationConfirmationModal from '#lib/components/admin/connectors/PublicationConfirmationModal.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';

  import AdminSidebarActionMenu from '#lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import { BrowserSelectionUrlAdapter } from '#lib/components/admin/shared/selection-url-port.js';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import OpenApiOperationCatalog from './OpenApiOperationCatalog.svelte';
  import { OpenApiConnectorListState } from './openapi-connector-list-state.svelte';
  import { OpenApiPublicationState } from './openapi-publication-state.svelte';

  type ActionData = {
    status?: string;
    mode?: 'file' | 'url';
    message?: string;
    retryable?: boolean;
    url?: string;
    approvedHosts?: string[];
    operationId?: string;
    activation_status?: string;
    connectorId?: string;
  } | null;

  type Props = {
    data: OpenApiConnectorListPageData & { selectedConnectorId?: string; selectedDetail?: OpenApiConnectorListItem; selectedDetailFailed?: true; invocationPolicies?: InvocationPolicyTool[] };
    form?: ActionData;
    unifiedRows?: readonly UnifiedConnectorRow[];
    unavailableKinds?: readonly UnifiedConnectorKind[];
    onconfigure: (event: MouseEvent, connector: OpenApiConnectorListItem) => void;
  };

  let { data, form = null, onconfigure, unifiedRows, unavailableKinds }: Props = $props();

  const connectors = $derived(data.connectors);
  const toast = useToast();
  const toolsRoute = new OpenApiConnectorToolsBrowserRoute();
  const detailsRoute = new OpenApiConnectorDetailsBrowserRoute();
  const initialSelectionId = untrack(() => (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? connectors[0]?.id);
  const state = new OpenApiConnectorListState({
    connectors: untrack(() => connectors),
    initialConnectorId: initialSelectionId,
    initialDetail: untrack(() => data.selectedDetail?.id === initialSelectionId ? data.selectedDetail : undefined),
    initialInvocationPolicies: untrack(() => data.selectedDetail?.id === initialSelectionId ? data.invocationPolicies : undefined),
    initialDetailFailed: untrack(() => data.selectedConnectorId === initialSelectionId ? data.selectedDetailFailed : false),
    loadTools: (connectorId) => toolsRoute.list(connectorId),
    loadDetail: (connectorId, signal) => detailsRoute.get(connectorId, signal),
    selectionUrl: new BrowserSelectionUrlAdapter({
      readUrl: () => new URL((page.shallow?.url ?? page.url).href),
      replaceUrl: (url) => { void goto(url, { shallow: true, replace: true, state: {} }).catch(() => toast.error('Could not update connector URL')); }
    })
  });
  onMount(() => {
    if (initialSelectionId && initialSelectionId !== data.selectedConnectorId) state.selectConnector(initialSelectionId);
  });
  const publication = new OpenApiPublicationState();
  const selectedConnector = $derived(state.resolveSelectedConnector());
  const selectedToolsState = $derived(selectedConnector ? state.tools.toolsState(selectedConnector) : null);
  const selectedCapability = $derived(parseConnectorCapability((page.shallow?.url ?? page.url).searchParams.get('capability')));
  const capabilityCounts = $derived({ tools: selectedToolsState?.status === 'ready' ? selectedToolsState.tools.length : 0, prompts: 0, resources: 0 });

  function loadToolsPanel(_node: HTMLElement): void {
    if (selectedConnector) void state.loadOperations(selectedConnector);
  }

  function requestPublicationConfirmation(event: MouseEvent, connectorName: string, actionLabel: 'Publish' | 'Unpublish'): void {
    if (!(event.currentTarget instanceof HTMLButtonElement) || !event.currentTarget.form) {
      return;
    }

    publication.request(event.currentTarget.form, connectorName, actionLabel);
  }

  function confirmPublication(): void {
    publication.confirm();
    state.view.closeMenu();
  }

  function cancelPublication(): void {
    publication.cancel();
    state.view.closeMenu();
  }

  function onToolsSaved(connectorId: string, savedTools: { operationId: string; activationStatus: OpenApiToolActivationStatus }[]): void {
    const submittedConnector = connectors.find((connector) => connector.id === connectorId);
    if (!submittedConnector) return;
    savedTools.forEach((tool) => state.tools.setActivation(submittedConnector, tool.operationId, tool.activationStatus));
  }
</script>

{#if state.view.capabilityDescriptionConnectorId}
  <CapabilityDescriptionOverrideModal kind="openapi" connectorId={state.view.capabilityDescriptionConnectorId} close={state.view.closeCapabilityDescription} />
{/if}

<PublicationConfirmationModal
  open={Boolean(publication.pendingPublication)}
  title={publication.modalTitle}
  message={publication.modalMessage}
  confirmLabel={publication.pendingPublication?.actionLabel ?? 'Confirm'}
  onconfirm={confirmPublication}
  oncancel={cancelPublication}
/>

  <UnifiedConnectorWorkspace kind="openapi" items={connectors} selectedId={selectedConnector?.id} {unifiedRows} {unavailableKinds} detailLabel="Selected OpenAPI connector detail" onselect={(connector) => state.selectConnector(connector.id)}>
    {#snippet metadata(connector)}
      <span class="connector-meta">OpenAPI · {connector.publicationStatus}</span>
    {/snippet}
    {#snippet actions(connector)}
      <AdminSidebarActionMenu open={state.view.openMenuConnectorId === connector.id} label={`Open actions for ${connector.name}`} onopenchange={(open) => state.setMenuOpen(connector.id, open)}>
        {#snippet menu()}
          <Button variant="unstyled" type="button" role="menuitem" onclick={(event) => { state.view.closeMenu(); onconfigure(event, connector); }}>Configure</Button>
          <Button variant="unstyled" type="button" role="menuitem" onclick={() => state.showCapabilityDescription(connector.id)}>Edit capability description</Button>
          {#if connector.canPublish || connector.canUnpublish}
            <ConnectorPublicationMenuAction connectorId={connector.id} connectorName={connector.name} action={connector.canPublish ? 'publish' : 'unpublish'} onrequest={requestPublicationConfirmation} />
          {/if}
        {/snippet}
      </AdminSidebarActionMenu>
    {/snippet}

    {#snippet detail()}
      {#if state.detailLoading}
        <div class="admin-message"><DelayedSpinner active label="Loading OpenAPI connector details" /></div>
      {:else if state.detailFailed}
        <div class="admin-message admin-message-error" role="alert"><p>OpenAPI connector details are unavailable.</p><Button onclick={state.retryDetail}>Try again</Button></div>
      {:else if selectedConnector}
      <ConnectorDetailSummary headingId="selected-openapi-connector-heading" title={selectedConnector.name} publicationStatus={selectedConnector.publicationStatus}>
        {#snippet description()}
          <p>{selectedConnector.capabilityDescription}</p>
        {/snippet}
        {#snippet statusOverview()}
          {#snippet updated()}<DateTimeView value={selectedConnector.updatedAt} />{/snippet}
          <ConnectorStatusOverview entries={[{ label: 'Updated', value: updated, icon: 'calendar' }]} />
        {/snippet}
        {#snippet technicalDetails()}
          <ConnectorReferenceGroup title="Identity">
            <ConnectorDetailItem label="Connector ID" variant="detail"><CopyableValue value={selectedConnector.id} inlineLabel="connector ID" /></ConnectorDetailItem>
          </ConnectorReferenceGroup>
        {/snippet}

        {#if (form?.status === 'stale' || form?.status === 'failed' || form?.status === 'conflict') && !form.mode}
          {#if form.connectorId === selectedConnector.id || !form.connectorId}
            <div class="admin-message admin-message-error" role="alert">
              <p>{form.message}</p>
            </div>
          {/if}
        {/if}

        <ConnectorCapabilities selected={selectedCapability} counts={capabilityCounts} currentUrl={new URL((page.shallow?.url ?? page.url).href)}>
        {#snippet children(activeCapability)}
        {#if activeCapability === 'tools'}
          {#key selectedConnector.id}
          <section class="panel-section" aria-labelledby="openapi-operations-heading" use:loadToolsPanel>
            <h3 id="openapi-operations-heading">Tools</h3>
            {#if selectedToolsState?.status === 'loading' || selectedToolsState?.status === 'idle'}
              <div role="status" aria-live="polite">
                <DelayedSpinner active label="Loading tools" inline size="small" />
              </div>
            {:else if selectedToolsState?.status === 'failed'}
              <div class="admin-message admin-message-error" role="alert">
                <p>Tools are unavailable. The connector remains available.</p>
                <Button onclick={() => state.tools.retry(selectedConnector)}>Try again</Button>
              </div>
            {:else if selectedToolsState?.status === 'ready'}
              {#key `${selectedConnector.id}:${selectedConnector.updatedAt}`}
                <OpenApiOperationCatalog
                  connectorId={selectedConnector.id}
                  tools={selectedToolsState.tools}
                  policies={state.policiesFor(selectedConnector.id)}
                  onsaved={onToolsSaved}
                />
              {/key}
            {/if}
          </section>
          {/key}
        {:else if activeCapability === 'prompts'}
          <PromptCatalog embedded catalog={emptyPromptCatalog()} />
        {:else}
          <ResourceCatalog embedded catalog={emptyResourceCatalog()} />
        {/if}
        {/snippet}
        </ConnectorCapabilities>
      </ConnectorDetailSummary>
      {/if}
    {/snippet}
  </UnifiedConnectorWorkspace>
<style>
  h3,
  p {
    margin: 0;
  }

  h3 {
    color: var(--admin-ink);
    font-size: 0.95rem;
    margin-bottom: 0.75rem;
  }

  .panel-section { min-width: 0; }

  .admin-message p {
    margin-top: 0;
  }

</style>
