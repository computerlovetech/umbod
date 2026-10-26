<script lang="ts">
  import { browserSubmit } from '$lib/admin/operations/browser-submit';
  import { page } from '$app/state';
  import type { BrowserSubmitFunction as SubmitFunction } from '$lib/admin/operations/browser-submit';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '$lib/admin/downstream-mcp-connectors';
  import { emptyPromptCatalog, emptyResourceCatalog, type PromptCatalog as PromptCatalogData, type ResourceCatalog as ResourceCatalogData } from '$lib/admin/capability-catalogs';
  import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import CapabilityDescriptionOverrideModal from '$lib/components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte';
  import ConnectorCapabilities from '$lib/components/admin/connectors/ConnectorCapabilities.svelte';
  import ConnectorDetailItem from '$lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import CopyableValue from '$lib/components/admin/connectors/CopyableValue.svelte';
  import ConnectorDetailSummary from '$lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorPublicationMenuAction from '$lib/components/admin/connectors/ConnectorPublicationMenuAction.svelte';
  import ConnectorSidebarList from '$lib/components/admin/connectors/ConnectorSidebarList.svelte';
  import PublicationConfirmationModal from '$lib/components/admin/connectors/PublicationConfirmationModal.svelte';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import AdminSidebarActionMenu from '$lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import DownstreamMcpSetupModal from './DownstreamMcpSetupModal.svelte';
  import DownstreamMcpToolCatalog from './DownstreamMcpToolCatalog.svelte';
  import DownstreamMcpPromptCatalog from './DownstreamMcpPromptCatalog.svelte';
  import DownstreamMcpResourceCatalog from './DownstreamMcpResourceCatalog.svelte';
  import { DownstreamMcpWorkspaceState, type DownstreamMcpCreateValues } from './downstream-mcp-workspace-state.svelte';
  import PersonalServerPolicyPanel from '../personal-mcp-servers/PersonalServerPolicyPanel.svelte';
  import { useToast } from '$lib/components/feedback';
  let { connectors, selected: detailSelected, catalog, promptCatalog, resourceCatalog, invocationPolicies = [], form, state }: { connectors: DownstreamMcpConnectorSummary[]; selected?: DownstreamMcpConnector; catalog?: DownstreamMcpToolList; promptCatalog?: PromptCatalogData; resourceCatalog?: ResourceCatalogData; invocationPolicies?: InvocationPolicyTool[]; form?: { message?: string; status?: string; mode?: string; values?: DownstreamMcpCreateValues }; state: DownstreamMcpWorkspaceState } = $props();
  type SidebarConnector = {
    id: string;
    name: string;
    iconDataUrl?: string;
    connector: DownstreamMcpConnectorSummary;
  };

  const confirmation = $derived(state.modal === 'delete');
  const toast = useToast();
  const selected = $derived(connectors.find((connector) => connector.connector_id === state.selectedConnectorId) ?? connectors[0]);
  const selectedDetailReady = $derived(detailSelected?.connector_id === selected?.connector_id && !state.detailLoading && !state.detailFailed);
  const sidebarConnectors = $derived(connectors.map((connector): SidebarConnector => ({ id: connector.connector_id, name: connector.display_name, iconDataUrl: connector.icon_url || undefined, connector })));
  const sharedMcpUri = $derived(detailSelected ? `${new URL(detailSelected.public_url).origin}/mcp` : '');
  const selectedCapability = $derived(parseConnectorCapability(page.url.searchParams.get('capability')));
  const capabilityCounts = $derived({
    tools: catalog?.tools.length ?? 0,
    prompts: promptCatalog?.prompts.length ?? 0,
    resources: resourceCatalog?.resources.length ?? 0
  });

  function requestPublicationConfirmation(event: MouseEvent, connectorName: string, actionLabel: 'Publish' | 'Unpublish'): void {
    if (!(event.currentTarget instanceof HTMLButtonElement) || !event.currentTarget.form) return;
    state.requestPublicationConfirmation(event.currentTarget.form, connectorName, actionLabel);
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
  }

  function mutationSubmit(action: 'refresh' | 'delete', connectorName: string): SubmitFunction {
    return ({ onComplete }) => {
      onComplete(state.finishSubmit);
      if (action === 'delete') state.beginSubmit();
      return async ({ result, update }) => {
        try {
          if (result.type === 'redirect') {
            if (action === 'delete') state.close();
            toast.success(action === 'refresh' ? `Refreshed discovery for ${connectorName}` : `${connectorName} deleted`);
          } else if (result.type === 'failure') {
            if (!isRecord(result.data) || !['failed', 'network', 'stale', 'conflict', 'authentication', 'invalid', 'unhealthy'].includes(String(result.data.status)) || typeof result.data.message !== 'string') {
              throw new Error(`Invalid ${action} MCP proxy connector result`);
            }
            if (result.data.status === 'unhealthy') toast.warning(result.data.message);
            else if (result.data.status === 'failed' || result.data.status === 'network') toast.error(result.data.message);
          } else {
            throw new Error(`Unexpected ${action} MCP proxy connector result`);
          }
          await update();
        } finally {
          if (action === 'delete' && result.type !== 'redirect') state.finishSubmit();
        }
      };
    };
  }
</script>
{#if !state.operations.authenticationLost}
<DownstreamMcpSetupModal {state} connector={state.modal === 'configure' ? detailSelected : undefined} message={form?.message} values={form?.mode === 'create' ? form.values : undefined} />
{#if state.capabilityDescriptionConnectorId}
  <CapabilityDescriptionOverrideModal kind="downstream_mcp" connectorId={state.capabilityDescriptionConnectorId} close={state.closeCapabilityDescription} />
{/if}
<PublicationConfirmationModal
  open={Boolean(state.operations.pending)}
  title={state.operations.pending ? `${state.operations.pending.action} ${state.operations.pending.name}?` : ''}
  message={state.operations.pending?.action === 'publish' ? 'Publication and current Group connector access trust all provider-exposed tools, including future tools after explicit rediscovery. Only explicitly permitted groups can select this server. Publication does not provide OAuth authorization, owner enablement or discovery.' : state.operations.pending?.action === 'delete' ? 'This permanently removes the server and saved local authorizations and policy. Existing connector and tool grants must be removed explicitly in Group permissions first; deletion never removes grants automatically. Remote tokens are not revoked.' : 'After catalogue reload, withdrawal prevents new selection. It does not revoke remote tokens or disconnect owners.'}
  confirmLabel={state.operations.pending?.action === 'delete' ? 'Delete server' : 'Confirm'}
  onconfirm={state.operations.confirm}
  oncancel={state.operations.cancel}
/>
<PublicationConfirmationModal
  open={Boolean(state.pendingPublication)}
  title={state.pendingPublication ? `${state.pendingPublication.actionLabel} ${state.pendingPublication.connectorName}?` : ''}
  message={state.pendingPublication ? `Please confirm that you want to ${state.pendingPublication.actionLabel.toLowerCase()} the MCP proxy connector ${state.pendingPublication.connectorName}.` : ''}
  confirmLabel={state.pendingPublication?.actionLabel ?? 'Confirm'}
  onconfirm={state.confirmPublication}
  oncancel={state.cancelPublication}
/>
{#if confirmation && selected}
  <div class="backdrop" role="presentation"><div class="confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"><h2 id="confirm-title">Delete connector?</h2><p>This permanently removes the connector and its discovered catalog.</p><form method="POST" data-operation={state.modal} use:browserSubmit={mutationSubmit('delete', selected.display_name)}><input type="hidden" name="connectorId" value={selected.connector_id} /><footer><Button variant="secondary" onclick={state.close}>Cancel</Button><Button type="submit" variant="danger" disabled={state.submitting}>{state.submitting ? 'Working…' : 'Confirm'}</Button></footer></form></div></div>
{/if}
{#if form?.message && (form.status === 'stale' || form.status === 'conflict' || form.status === 'authentication' || form.status === 'invalid')}<p class="feedback" role="alert">{form.message}</p>{/if}
{#if state.operations.message}<p role="alert" class="feedback">{state.operations.message} <a href="/admin/group-permissions/connectors">Group permissions</a></p>{/if}
{#if state.operations.blocked}<Button onclick={state.operations.reload}>Reload servers</Button>{/if}
{#if connectors.length && selected && !state.operations.blocked}
<AdminSplitWorkspace ariaLabel="MCP connectors workspace" sidebarLabel="MCP connectors" sidebarHeading="Connectors" count={connectors.length} detailLabel="Selected MCP connector detail">
 {#snippet sidebar()}
  <ConnectorSidebarList items={sidebarConnectors} selectedId={selected.connector_id} ariaLabel="MCP connectors" onselect={(connector) => state.selectConnector(connector.id)}>
   {#snippet metadata(item)}
    <span class="connector-meta">{item.connector.authorization_mode === 'personal' ? 'Personal authorization' : 'Shared authorization'} · {item.connector.authorization_mode === 'shared' ? `${item.connector.health.status} · ` : ''}{item.connector.publication_status}</span>
   {/snippet}
   {#snippet actions(item)}
    {#if item.id === selected.connector_id}<AdminSidebarActionMenu open={state.menuOpen} label={`Open actions for ${item.name}`} onopenchange={state.setMenuOpen}>{#snippet menu()}{#if selected.authorization_mode === 'shared'}<button role="menuitem" type="button" onclick={(event) => state.open('configure', event.currentTarget, detailSelected)}>Configure</button><button role="menuitem" type="button" onclick={(event) => state.openCapabilityDescription(selected.connector_id, event.currentTarget)}>Edit capability description</button><form method="POST" data-operation="refresh" use:browserSubmit={mutationSubmit('refresh', selected.display_name)}><input type="hidden" name="connectorId" value={selected.connector_id}/><button role="menuitem">Refresh discovery</button></form>{/if}{#if selected.authorization_mode === 'personal'}<button role="menuitem" disabled={state.operations.locked} onclick={() => state.operations.request(selected.publication_status === 'published' ? 'unpublish' : 'publish', selected.connector_id, selected.display_name)}>{selected.publication_status === 'published' ? 'Unpublish' : 'Publish'}</button><button role="menuitem" disabled={state.operations.locked} onclick={() => state.operations.request('delete', selected.connector_id, selected.display_name)}>Delete</button>{:else}<ConnectorPublicationMenuAction connectorId={selected.connector_id} connectorName={selected.display_name} action={selected.publication_status === 'published' ? 'unpublish' : 'publish'} role="menuitem" onrequest={requestPublicationConfirmation} /><button role="menuitem" class="danger-text" type="button" onclick={(event) => state.open('delete', event.currentTarget)}>Delete</button>{/if}{/snippet}</AdminSidebarActionMenu>{/if}
   {/snippet}
  </ConnectorSidebarList>
 {/snippet}
 {#snippet detail()}
 {#if state.detailLoading}<div class="feedback"><DelayedSpinner active label="Loading MCP connector details" /></div>
 {:else if state.detailFailed}<div class="feedback" role="alert"><p>Connector details are unavailable.</p><Button onclick={state.retrySelected}>Try again</Button></div>
 {:else if selectedDetailReady && detailSelected}<ConnectorDetailSummary headingId="selected-mcp-connector-heading" title={detailSelected.display_name} iconDataUrl={detailSelected.icon_url || undefined} publicationStatus={detailSelected.publication_status}>
  {#snippet description()}<p>{detailSelected.capability_description}</p>{/snippet}
  {#snippet summary()}
   <ConnectorDetailItem label="Authorization mode" tone="neutral">{detailSelected.authorization_mode === 'personal' ? 'Personal' : 'Shared'}</ConnectorDetailItem>
   {#if detailSelected.authorization_mode === 'shared'}
   <ConnectorDetailItem label="Discovery health" tone={detailSelected.health.status === 'healthy' ? 'success' : detailSelected.health.status === 'unhealthy' ? 'danger' : 'warning'}>{detailSelected.health.status}</ConnectorDetailItem>
   <ConnectorDetailItem label="Authentication" tone={detailSelected.auth_mode === 'none' ? 'neutral' : detailSelected.credential_configured ? 'success' : 'warning'}>{detailSelected.auth_mode === 'none' ? 'Not required' : detailSelected.credential_configured ? 'Bearer token configured' : 'Bearer token missing'}</ConnectorDetailItem>
   <ConnectorDetailItem label="Discovered tools" tone="neutral">{catalog?.tools.length ?? 0} tools</ConnectorDetailItem>
   {/if}
  {/snippet}
  {#snippet technicalDetails()}
   <ConnectorDetailItem label={detailSelected.authorization_mode === 'personal' ? 'Server ID' : 'Connector ID'} variant="detail"><code>{detailSelected.connector_id}</code></ConnectorDetailItem>
   <ConnectorDetailItem label="Downstream endpoint" variant="detail"><code>{detailSelected.endpoint_url}</code></ConnectorDetailItem>
   <ConnectorDetailItem label="Tool name prefix" variant="detail"><code>{detailSelected.tool_name_prefix}</code></ConnectorDetailItem>
   {#if detailSelected.authorization_mode === 'personal'}
   <ConnectorDetailItem label="Registration path" variant="detail"><code>{detailSelected.public_path}</code></ConnectorDetailItem>
   {:else}
   <ConnectorDetailItem label="Shared endpoint" variant="detail"><CopyableValue value={sharedMcpUri} /></ConnectorDetailItem>
   <ConnectorDetailItem label="Dedicated endpoint" variant="detail"><CopyableValue value={detailSelected.public_url} /></ConnectorDetailItem>
   <ConnectorDetailItem label="Discovery detail" variant="detail">{#if detailSelected.health.reason}{detailSelected.health.reason}{:else}No discovery issue reported{/if}</ConnectorDetailItem>
   <ConnectorDetailItem label="Last attempt / success" variant="detail"><div class="datetime-pair"><span><strong>Attempt</strong>{#if detailSelected.health.checked_at}<DateTimeView value={detailSelected.health.checked_at} />{:else}Not attempted{/if}</span><span><strong>Success</strong>{#if catalog?.discovered_at}<DateTimeView value={catalog.discovered_at} />{:else}No successful discovery{/if}</span></div></ConnectorDetailItem>
   {/if}
  {/snippet}
  {#if detailSelected.authorization_mode === 'personal'}
    {#if !state.operations.pending && !state.operations.busy}
    {#key detailSelected.connector_id}<PersonalServerPolicyPanel connectorId={detailSelected.connector_id} accessLost={state.operations.loseAccess} lockChanged={state.operations.setFormLocked} externalLocked={state.operations.busy} />{/key}
    {/if}
  {:else}
  <ConnectorCapabilities selected={selectedCapability} counts={capabilityCounts} currentUrl={page.url}>
   {#snippet children(activeCapability)}
   {#if activeCapability === 'tools'}
    <section class="tools" aria-labelledby="mcp-tools-heading"><h3 id="mcp-tools-heading">Tools</h3>{#key detailSelected.connector_id}<DownstreamMcpToolCatalog connectorId={detailSelected.connector_id} tools={catalog?.tools ?? []} policies={invocationPolicies} onsaved={(connectorId, tools) => state.reconcileTools(connectorId, tools)} />{/key}</section>
   {:else if activeCapability === 'prompts'}
    {#key detailSelected.connector_id}<DownstreamMcpPromptCatalog connectorId={detailSelected.connector_id} catalog={promptCatalog ?? emptyPromptCatalog()} onsaved={(connectorId, nextCatalog) => state.reconcilePrompts(connectorId, nextCatalog)} />{/key}
   {:else}
    {#key detailSelected.connector_id}<DownstreamMcpResourceCatalog connectorId={detailSelected.connector_id} catalog={resourceCatalog ?? emptyResourceCatalog()} onsaved={(connectorId, nextCatalog) => state.reconcileResources(connectorId, nextCatalog)} />{/key}
   {/if}
   {/snippet}
  </ConnectorCapabilities>
  {/if}
 </ConnectorDetailSummary>
 {/if}
 {/snippet}
</AdminSplitWorkspace>
{:else if !state.operations.blocked}<p class="empty">No MCP connectors yet.</p>{/if}
{:else}<p role="alert">Administration access was lost. Sign in again before reloading this page.</p>{/if}
<style>
  button:not(:disabled){cursor:pointer}
  button:disabled{cursor:not-allowed}
  .datetime-pair { display: grid; gap: .35rem; }
  .datetime-pair span { display: grid; gap: .1rem; }
  .datetime-pair strong { color: var(--admin-muted); font-size: 11px; font-weight: 600; }
  .tools h3 { color: var(--admin-ink); font-size: 1rem; margin: 0 0 .875rem; }
  .backdrop { align-items: center; background: var(--admin-overlay); display: flex; inset: 0; justify-content: center; padding: 1rem; position: fixed; z-index: 110; }
  .confirm { background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); box-shadow: var(--admin-shadow-dialog); box-sizing: border-box; color: var(--admin-ink); max-height: calc(100dvh - 2rem); overflow-y: auto; padding: 1.5rem; width: min(28rem, 100%); }
  .confirm h2 { font-size: 1.25rem; font-weight: 600; letter-spacing: -.03em; margin: 0; }
  .confirm p { color: var(--admin-muted); font-size: 14px; line-height: 1.55; margin: 1rem 0 1.5rem; }
  .confirm footer { border-top: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: .7rem; justify-content: flex-end; padding-top: 1rem; }
  .danger-text[role='menuitem'] { color: var(--admin-danger-text); }
  .feedback, .empty { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-muted); font-size: 14px; line-height: 1.55; padding: 1rem; }
  .feedback[role='alert'] { background: var(--admin-danger-bg); border-color: var(--admin-danger-border); color: var(--admin-danger-text); }
  .feedback p { margin: 0 0 .75rem; }
</style>
