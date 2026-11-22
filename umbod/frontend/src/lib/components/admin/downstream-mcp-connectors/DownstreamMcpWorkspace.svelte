<script lang="ts">
  import { browserSubmit } from '#lib/admin/operations/browser-submit.js';
  import { page } from '$app/state';
  import type { BrowserSubmitFunction as SubmitFunction } from '#lib/admin/operations/browser-submit.js';
  import { parseConnectorCapability } from '#lib/admin/connector-capabilities.js';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '#lib/admin/downstream-mcp-connectors.js';
  import { emptyPromptCatalog, emptyResourceCatalog, type PromptCatalog as PromptCatalogData, type ResourceCatalog as ResourceCatalogData } from '#lib/admin/capability-catalogs.js';
  import type { InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
  import CapabilityDescriptionOverrideModal from '#lib/components/admin/capability-descriptions/CapabilityDescriptionOverrideModal.svelte';
  import ConnectorCapabilities from '#lib/components/admin/connectors/ConnectorCapabilities.svelte';
  import ConnectorDetailItem from '#lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import CopyableValue from '#lib/components/admin/connectors/CopyableValue.svelte';
  import ConnectorStatusOverview, { type ConnectorStatusSpotlight } from '../connectors/ConnectorStatusOverview.svelte';
  import ConnectorDetailSummary from '#lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorReferenceGroup from '#lib/components/admin/connectors/ConnectorReferenceGroup.svelte';
  import UnifiedConnectorWorkspace from '#lib/components/admin/connectors/UnifiedConnectorWorkspace.svelte';
  import type { UnifiedConnectorKind, UnifiedConnectorRow } from '#lib/admin/unified-connectors.js';
  import PublicationConfirmationModal from '#lib/components/admin/connectors/PublicationConfirmationModal.svelte';

  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import AdminSidebarActionMenu from '#lib/components/admin/shared/AdminSidebarActionMenu.svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import DownstreamMcpSetupModal from './DownstreamMcpSetupModal.svelte';
  import DownstreamMcpToolCatalog from './DownstreamMcpToolCatalog.svelte';
  import DownstreamMcpPromptCatalog from './DownstreamMcpPromptCatalog.svelte';
  import DownstreamMcpResourceCatalog from './DownstreamMcpResourceCatalog.svelte';
  import { DownstreamMcpWorkspaceState, type DownstreamMcpCreateValues } from './downstream-mcp-workspace-state.svelte';
  import PersonalServerEditDialog from '../personal-mcp-servers/PersonalServerEditDialog.svelte';
  import PersonalMcpDetails from '../personal-mcp-servers/PersonalMcpDetails.svelte';
  import PersonalMcpPublicationModal from '../personal-mcp-servers/PersonalMcpPublicationModal.svelte';
  import PersonalOAuthSetupDialog from '../personal-mcp-servers/PersonalOAuthSetupDialog.svelte';
  import { useToast } from '#lib/components/feedback/index.js';
  let { connectors, selected: loadedDetail, catalog, promptCatalog, resourceCatalog, invocationPolicies = [], form, state, unifiedRows, unavailableKinds }: { unifiedRows?: readonly UnifiedConnectorRow[]; unavailableKinds?: readonly UnifiedConnectorKind[]; connectors: DownstreamMcpConnectorSummary[]; selected?: DownstreamMcpConnector; catalog?: DownstreamMcpToolList; promptCatalog?: PromptCatalogData; resourceCatalog?: ResourceCatalogData; invocationPolicies?: InvocationPolicyTool[]; form?: { message?: string; status?: string; mode?: string; values?: DownstreamMcpCreateValues }; state: DownstreamMcpWorkspaceState } = $props();
  type SidebarConnector = {
    id: string;
    name: string;
    iconDataUrl?: string;
    connector: DownstreamMcpConnectorSummary;
  };

  const confirmation = $derived(state.modal === 'delete');
  const toast = useToast();
  const currentConnectors = $derived(connectors.map((connector) => ({ ...connector, publication_status: state.operations.publicationStatuses.get(connector.connector_id) ?? connector.publication_status })));
  const detailSelected = $derived(loadedDetail ? { ...loadedDetail, publication_status: state.operations.publicationStatuses.get(loadedDetail.connector_id) ?? loadedDetail.publication_status } : undefined);
  const selected = $derived(currentConnectors.find((connector) => connector.connector_id === state.selectedConnectorId) ?? currentConnectors[0]);
  const selectedDetailReady = $derived(detailSelected?.connector_id === selected?.connector_id && !state.detailLoading && !state.detailFailed);
  const sidebarConnectors = $derived(currentConnectors.map((connector): SidebarConnector => ({ id: connector.connector_id, name: connector.display_name, iconDataUrl: connector.icon_url || undefined, connector })));
  const sharedMcpUri = $derived(detailSelected ? `${new URL(detailSelected.public_url).origin}/mcp` : '');
  const selectedCapability = $derived(parseConnectorCapability((page.shallow?.url ?? page.url).searchParams.get('capability')));
  const capabilityCounts = $derived({
    tools: catalog?.tools.length ?? 0,
    prompts: promptCatalog?.prompts.length ?? 0,
    resources: resourceCatalog?.resources.length ?? 0
  });

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
  const credentialNames = { bearer: 'Bearer token', basic: 'Basic auth credential', custom: 'Custom header credential' } as const;

  const discoveryIndicators = {
    healthy: { value: 'Healthy', icon: 'check', tone: 'success' },
    unhealthy: { value: 'Discovery failed', icon: 'failed', tone: 'danger' },
    unknown: { value: 'Unknown', icon: 'unknown', tone: 'neutral' }
  } as const;
</script>
{#if !state.operations.authenticationLost}
<DownstreamMcpSetupModal {state} connector={state.modal === 'configure' ? detailSelected : undefined} message={form?.message} values={form?.mode === 'create' ? form.values : undefined} />
{#if state.modal === 'personal-edit' && detailSelected?.authorization_mode === 'personal'}
  <PersonalServerEditDialog connectorId={detailSelected.connector_id} close={state.close} accessLost={state.operations.loseAccess} lockChanged={state.operations.setFormLocked} reconciliationRequired={state.operations.requireReload} saved={state.personalSetup.policyChanged} proposal={state.personalSetup.editProposal} />
{/if}
{#if state.modal === 'personal-setup' && detailSelected?.authorization_mode === 'personal'}
  <PersonalOAuthSetupDialog state={state.personalSetup} close={state.close} edit={(trigger) => state.open('personal-edit', trigger, detailSelected)} published={detailSelected.publication_status === 'published'} publish={() => state.publishChecked(detailSelected)} />
{/if}
{#if state.capabilityDescriptionConnectorId}
  <CapabilityDescriptionOverrideModal kind="downstream_mcp" connectorId={state.capabilityDescriptionConnectorId} close={state.closeCapabilityDescription} />
{/if}
{#if state.operations.pending?.action === 'publish' && connectors.find((connector) => connector.connector_id === state.operations.pending?.id)?.authorization_mode === 'personal'}
  <PersonalMcpPublicationModal name={state.operations.pending.name} onconfirm={state.confirmPublication} oncancel={state.cancelPublication} />
{:else}
<PublicationConfirmationModal
  open={Boolean(state.operations.pending)}
  title={state.operations.pending ? `${state.operations.pending.action === 'publish' ? 'Publish' : state.operations.pending.action === 'unpublish' ? 'Unpublish' : 'Delete'} ${state.operations.pending.name}?` : ''}
  message={state.operations.pending && state.operations.pending.action !== 'delete' && connectors.find((connector) => connector.connector_id === state.operations.pending?.id)?.authorization_mode === 'shared' ? `Please confirm that you want to ${state.operations.pending.action} the MCP proxy connector ${state.operations.pending.name}.` : state.operations.pending?.action === 'delete' ? 'This permanently removes the server and saved local authorizations and policy. Existing connector and tool grants must be removed explicitly in Permissions first; deletion never removes grants automatically. Remote tokens are not revoked.' : 'After catalogue reload, withdrawal prevents new selection. It does not revoke remote tokens or disconnect owners.'}
  confirmLabel={state.operations.pending?.action === 'delete' ? 'Delete server' : state.operations.pending?.action === 'unpublish' ? 'Unpublish' : 'Publish'}
  onconfirm={state.confirmPublication}
  oncancel={state.cancelPublication}
/>
{/if}
{#if confirmation && selected}
  <ModalShell title="Delete connector?" titleId="confirm-title" descriptionId="confirm-description" close={state.close} closeDisabled={state.submitting} role="alertdialog" --modal-width="28rem" --modal-overflow="auto">
    <p id="confirm-description" class="deletion-description">This permanently removes the connector and its discovered catalog.</p>
    <form method="POST" data-operation={state.modal} use:browserSubmit={mutationSubmit('delete', selected.display_name)}>
      <input type="hidden" name="connectorId" value={selected.connector_id} />
      <footer class="deletion-actions">
        <Button variant="secondary" type="button" data-dialog-cancel disabled={state.submitting} onclick={state.close}>Cancel</Button>
        <Button type="submit" variant="danger" disabled={state.submitting}>{state.submitting ? 'Working…' : 'Confirm'}</Button>
      </footer>
    </form>
  </ModalShell>
{/if}
{#if form?.message && (form.status === 'stale' || form.status === 'conflict' || form.status === 'authentication' || form.status === 'invalid')}<p class="feedback" role="alert">{form.message}</p>{/if}
{#if state.operations.busy}<p role="status" class="feedback">Updating MCP connector…</p>{/if}
{#if state.operations.message}<p role="alert" class="feedback">{state.operations.message} <a href="/admin/group-permissions/connectors">Permissions</a></p>{/if}
{#if state.operations.blocked}<Button onclick={state.operations.reload}>Reload servers</Button>{/if}
{#if !state.operations.blocked}
<UnifiedConnectorWorkspace kind="mcp" items={sidebarConnectors} selectedId={selected?.connector_id} {unifiedRows} {unavailableKinds} detailLabel="Selected MCP connector detail" onselect={(connector) => state.selectConnector(connector.id)}>
   {#snippet metadata(item)}
    <span class="connector-meta">MCP · {item.connector.authorization_mode === 'personal' ? 'Personal authorization' : 'Shared authorization'} · {item.connector.authorization_mode === 'shared' ? `${item.connector.health.status} · ` : ''}{item.connector.publication_status}{#if item.connector.authorization_mode === 'personal'}{' · '}<span role="status">{state.personalSetup.sidebarLabel(item.id)}</span>{/if}</span>
   {/snippet}
   {#snippet actions(item)}
    {#if selected && item.id === selected.connector_id}<AdminSidebarActionMenu open={state.menuOpen} label={`Open actions for ${item.name}`} onopenchange={state.setMenuOpen}>{#snippet menu()}{#if selected.authorization_mode === 'personal'}<button role="menuitem" type="button" disabled={state.operations.locked || !selectedDetailReady} onclick={(event) => state.open('personal-edit', event.currentTarget, detailSelected)}>Edit</button><button role="menuitem" type="button" disabled={state.operations.locked || !selectedDetailReady} onclick={(event) => state.checkConfiguration(event.currentTarget, detailSelected)}>Check configuration</button>{/if}{#if selected.authorization_mode === 'shared'}<button role="menuitem" type="button" disabled={state.operations.locked} onclick={(event) => state.open('configure', event.currentTarget, detailSelected)}>Configure</button><button role="menuitem" type="button" disabled={state.operations.locked} onclick={(event) => state.openCapabilityDescription(selected.connector_id, event.currentTarget)}>Edit capability description</button><form method="POST" data-operation="refresh" use:browserSubmit={mutationSubmit('refresh', selected.display_name)}><input type="hidden" name="connectorId" value={selected.connector_id}/><button role="menuitem" disabled={state.operations.locked}>Refresh discovery</button></form>{/if}{#if selected.publication_status === 'published' || state.operations.canPublish(selected)}<button role="menuitem" type="button" disabled={state.operations.locked} onclick={() => state.requestPublication(selected)}>{selected.publication_status === 'published' ? 'Unpublish' : 'Publish'}</button>{/if}{#if selected.authorization_mode === 'personal'}<button role="menuitem" class="danger-text" disabled={state.operations.locked} onclick={() => state.operations.request('delete', selected.connector_id, selected.display_name)}>Delete</button>{:else}<button role="menuitem" class="danger-text" type="button" disabled={state.operations.locked} onclick={(event) => state.open('delete', event.currentTarget)}>Delete</button>{/if}{/snippet}</AdminSidebarActionMenu>{/if}
   {/snippet}

 {#snippet detail()}
 {#if state.detailLoading}<div class="feedback"><DelayedSpinner active label="Loading MCP connector details" /></div>
 {:else if state.detailFailed}<div class="feedback" role="alert"><p>Connector details are unavailable.</p><Button onclick={state.retrySelected}>Try again</Button></div>
 {:else if selectedDetailReady && detailSelected}<ConnectorDetailSummary headingId="selected-mcp-connector-heading" title={detailSelected.display_name} iconDataUrl={detailSelected.icon_url || undefined} publicationStatus={detailSelected.publication_status}>
  {#snippet description()}{#if detailSelected.authorization_mode === 'shared'}<p>{detailSelected.capability_description}</p>{/if}{/snippet}
  {#snippet statusOverview()}
   {#if detailSelected.authorization_mode === 'shared'}
    {@const authenticationRequired = detailSelected.auth_mode === 'static_bearer'}
    {@const missingCredential = authenticationRequired && !detailSelected.credential_configured}
    {@const credentialName = credentialNames[detailSelected.header_type]}
    {@const authentication = {
      label: 'Authentication',
      value: authenticationRequired ? `${credentialName} ${missingCredential ? 'missing' : 'configured'}` : 'Not required',
      icon: missingCredential ? 'warning' : authenticationRequired ? 'lock' : 'open',
      tone: missingCredential ? 'warning' : 'neutral'
    } satisfies ConnectorStatusSpotlight}
    {@const discoveryStatus = detailSelected.health.status}
    {@const discovery = {
      label: 'Discovery health',
      ...discoveryIndicators[discoveryStatus],
      value: discoveryStatus === 'unknown' && !detailSelected.health.checked_at ? 'Not checked' : discoveryIndicators[discoveryStatus].value
    } satisfies ConnectorStatusSpotlight}
    {@const toolCount = catalog?.tools.length ?? 0}
    <ConnectorStatusOverview spotlight={missingCredential ? authentication : discovery} entries={[
      { label: 'Authorization mode', value: 'Shared', icon: 'shared' },
      missingCredential ? discovery : authentication,
      { label: 'Discovered tools', value: toolCount === 1 ? '1 tool' : `${toolCount} tools`, icon: 'tools' }
    ]} />
   {:else}
    {#key detailSelected.connector_id}
      <PersonalMcpDetails
        state={state.personalSetup}
        connectorId={detailSelected.connector_id}
        locked={state.operations.locked}
        oncheck={(trigger) => state.checkConfiguration(trigger, detailSelected)}
        onreview={(trigger) => state.open('personal-setup', trigger, detailSelected)}
      />
    {/key}
   {/if}
  {/snippet}
  {#snippet technicalDetails()}
   {@const personal = detailSelected.authorization_mode === 'personal'}
   <ConnectorReferenceGroup title={personal ? 'Connection' : 'Endpoints'}>
    {#if personal}
     <ConnectorDetailItem label="Registration path" variant="detail"><CopyableValue value={detailSelected.public_path} inlineLabel="registration path" /></ConnectorDetailItem>
    {:else}
     <ConnectorDetailItem label="Shared endpoint" variant="detail"><CopyableValue value={sharedMcpUri} inlineLabel="shared endpoint" /></ConnectorDetailItem>
     <ConnectorDetailItem label="Dedicated endpoint" variant="detail"><CopyableValue value={detailSelected.public_url} inlineLabel="dedicated endpoint" /></ConnectorDetailItem>
    {/if}
    <ConnectorDetailItem label="Downstream endpoint" variant="detail"><CopyableValue value={detailSelected.endpoint_url} inlineLabel="downstream endpoint" /></ConnectorDetailItem>
   </ConnectorReferenceGroup>
   {#if !personal}
    <ConnectorReferenceGroup title="Discovery">
     <ConnectorDetailItem label="Discovery detail" variant="detail">{detailSelected.health.reason || 'No discovery issue reported'}</ConnectorDetailItem>
     <ConnectorDetailItem label="Last attempt" variant="detail">{#if detailSelected.health.checked_at}<DateTimeView value={detailSelected.health.checked_at} />{:else}Not attempted{/if}</ConnectorDetailItem>
     <ConnectorDetailItem label="Last success" variant="detail">{#if catalog?.discovered_at}<DateTimeView value={catalog.discovered_at} />{:else}No successful discovery{/if}</ConnectorDetailItem>
    </ConnectorReferenceGroup>
   {/if}
   <ConnectorReferenceGroup title="Identity">
    <ConnectorDetailItem label={personal ? 'Server ID' : 'Connector ID'} variant="detail"><CopyableValue value={detailSelected.connector_id} inlineLabel={personal ? 'server ID' : 'connector ID'} /></ConnectorDetailItem>
    <ConnectorDetailItem label="Tool name prefix" variant="detail"><CopyableValue value={detailSelected.tool_name_prefix} inlineLabel="tool name prefix" /></ConnectorDetailItem>
   </ConnectorReferenceGroup>
  {/snippet}
  {#if detailSelected.authorization_mode === 'shared'}
  <ConnectorCapabilities selected={selectedCapability} counts={capabilityCounts} currentUrl={new URL((page.shallow?.url ?? page.url).href)}>
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
</UnifiedConnectorWorkspace>
{/if}
{:else}<p role="alert">Administration access was lost. Sign in again before reloading this page.</p>{/if}
<style>
  button:not(:disabled){cursor:pointer}
  button:disabled{cursor:not-allowed}
  .tools h3 { color: var(--admin-ink); font-size: 1rem; margin: 0 0 .875rem; }
  .deletion-description { color: var(--admin-muted); font-size: 14px; line-height: 1.55; margin: 1rem 0 1.5rem; }
  .deletion-actions { border-top: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: .7rem; justify-content: flex-end; padding-top: 1rem; }
  .danger-text[role='menuitem'] { color: var(--admin-danger-text); }
  .feedback { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); color: var(--admin-muted); font-size: 14px; line-height: 1.55; padding: 1rem; }
  .feedback[role='alert'] { background: var(--admin-danger-bg); border-color: var(--admin-danger-border); color: var(--admin-danger-text); }
  .feedback p { margin: 0 0 .75rem; }
</style>
