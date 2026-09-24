<script lang="ts">
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import { OpenApiConnectorToolsBrowserRoute } from '$lib/admin/openapi-connector-tools-browser-api';
  import { OpenApiConnectorDetailsBrowserRoute } from '$lib/admin/openapi-connector-details-browser-api';
  import type { OpenApiConnectorListItem, OpenApiConnectorListPageData, OpenApiToolActivationStatus } from '$lib/admin/openapi-connectors';
  import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import { emptyPromptCatalog, emptyResourceCatalog } from '$lib/admin/capability-catalogs';
  import PromptCatalog from '$lib/components/admin/capability-catalogs/PromptCatalog.svelte';
  import ResourceCatalog from '$lib/components/admin/capability-catalogs/ResourceCatalog.svelte';
  import CapabilityDescriptionOverrideModal from '$lib/components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte';
  import ConnectorCapabilities from '$lib/components/admin/connectors/ConnectorCapabilities.svelte';
  import ConnectorDetailItem from '$lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import ConnectorDetailSummary from '$lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorPublicationMenuAction from '$lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte';
  import ConnectorSidebarList from '$lib/components/admin/connectors/ConnectorSidebarList.svelte';
  import PublicationConfirmationModal from '$lib/components/admin/connectors/PublicationConfirmationModal.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import { BrowserSelectionUrlAdapter } from '$lib/components/admin/shared/selection-url-port';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import OpenApiOperationCatalog from './OpenApiOperationCatalog.svelte';
  import { OpenApiConnectorListState } from './openapi-connector-list-state.svelte';
  import { OpenApiConnectorReloadState } from './openapi-connector-reload-state.svelte';
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
    onretry: () => Promise<void>;
    onconfigure: (event: MouseEvent, connector: OpenApiConnectorListItem) => void;
  };

  let { data, form = null, onretry, onconfigure }: Props = $props();

  const connectors = $derived(data.status === 'ready' || data.status === 'empty' ? data.connectors : []);
  const toolsRoute = new OpenApiConnectorToolsBrowserRoute();
  const detailsRoute = new OpenApiConnectorDetailsBrowserRoute();
  const state = new OpenApiConnectorListState({
    connectors: untrack(() => connectors),
    initialConnectorId: untrack(() => data.selectedConnectorId ?? page.url.searchParams.get('connector')),
    initialDetail: untrack(() => data.selectedDetail),
    initialInvocationPolicies: untrack(() => data.invocationPolicies),
    initialDetailFailed: untrack(() => data.selectedDetailFailed),
    loadTools: (connectorId) => toolsRoute.list(connectorId),
    loadDetail: (connectorId, signal) => detailsRoute.get(connectorId, signal),
    selectionUrl: new BrowserSelectionUrlAdapter({ readUrl: () => page.url, replaceUrl: (url) => replaceState(url, {}) })
  });
  const publication = new OpenApiPublicationState();
  const reload = new OpenApiConnectorReloadState(() => onretry());
  const selectedConnector = $derived(state.resolveSelectedConnector());
  const selectedToolsState = $derived(selectedConnector ? state.tools.toolsState(selectedConnector) : null);
  const selectedCapability = $derived(parseConnectorCapability(page.url.searchParams.get('capability')));
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

{#if data.status === 'ready' && selectedConnector}
  <AdminSplitWorkspace
    ariaLabel="OpenAPI connectors workspace"
    sidebarLabel="OpenAPI connectors"
    sidebarHeading="OpenAPI connectors"
    count={connectors.length}
    detailLabel="Selected OpenAPI connector detail"
  >
    {#snippet sidebar()}
      <ConnectorSidebarList items={connectors} selectedId={selectedConnector.id} ariaLabel="OpenAPI connectors" onselect={(connector) => state.selectConnector(connector.id)}>
        {#snippet metadata(connector)}
          <span class="connector-meta">{connector.publicationStatus}</span>
        {/snippet}
        {#snippet actions(connector)}
          <AdminSidebarActionMenu open={state.view.openMenuConnectorId === connector.id} label={`Open actions for ${connector.name}`} onopenchange={(open) => state.setMenuOpen(connector.id, open)}>
            {#snippet menu()}
              <button type="button" role="menuitem" onclick={(event) => { state.view.closeMenu(); onconfigure(event, connector); }}>Configure</button>
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
        <div class="admin-message"><DelayedSpinner active label="Loading OpenAPI connector details" /></div>
      {:else if state.detailFailed}
        <div class="admin-message admin-message-error" role="alert"><p>OpenAPI connector details are unavailable.</p><Button onclick={state.retryDetail}>Try again</Button></div>
      {:else}
      <ConnectorDetailSummary headingId="selected-openapi-connector-heading" title={selectedConnector.name} publicationStatus={selectedConnector.publicationStatus}>
        {#snippet description()}
          <p>{selectedConnector.capabilityDescription}</p>
        {/snippet}
        {#snippet summary()}
          <ConnectorDetailItem label="Updated" tone="neutral"><DateTimeView value={selectedConnector.updatedAt} /></ConnectorDetailItem>
          <ConnectorDetailItem label="Status" tone={selectedConnector.publicationStatus === 'published' ? 'success' : 'neutral'}>{selectedConnector.publicationStatus}</ConnectorDetailItem>
        {/snippet}
        {#snippet technicalDetails()}
          <ConnectorDetailItem label="Connector ID" variant="detail"><code>{selectedConnector.id}</code></ConnectorDetailItem>
        {/snippet}

        {#if (form?.status === 'stale' || form?.status === 'failed' || form?.status === 'conflict') && !form.mode}
          {#if form.connectorId === selectedConnector.id || !form.connectorId}
            <div class="admin-message admin-message-error" role="alert">
              <p>{form.message}</p>
            </div>
          {/if}
        {/if}

        <ConnectorCapabilities selected={selectedCapability} counts={capabilityCounts} currentUrl={page.url}>
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
  </AdminSplitWorkspace>
{:else if data.status === 'empty'}
  <p class="empty-note">{data.message}</p>
{:else if data.status === 'failed'}
  <div class="admin-message admin-message-error failure" role="alert">
    <p>{data.message}</p>
    <Button disabled={reload.retrying} onclick={reload.retry}>
      {#if reload.retrying}
        <DelayedSpinner active={reload.retrying} label="Loading OpenAPI connectors" inline size="small" />
      {:else}
        {data.retryLabel}
      {/if}
    </Button>
  </div>
{:else}
  <p class="empty-note">No OpenAPI connectors are available yet.</p>
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

  .panel-section { min-width: 0; }

  .empty-note {
    background: #fbfbfa;
    border: 1px solid #e9e9e7;
    border-radius: 10px;
    color: #787774;
    margin: 1.5rem 0 0;
    padding: 1rem;
  }

  .failure p {
    margin: 0 0 12px;
  }

  .admin-message p {
    margin-top: 0;
  }

</style>
