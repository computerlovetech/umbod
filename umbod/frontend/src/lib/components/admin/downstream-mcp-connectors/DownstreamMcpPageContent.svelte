<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { useToast } from '#lib/components/feedback/index.js';
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { PersonalServerFormState } from '../personal-mcp-servers/personal-server-form-state.svelte';
  import PersonalServerRegistration from '../personal-mcp-servers/PersonalServerRegistration.svelte';
  import McpEndpointSetupWizard from './McpEndpointSetupWizard.svelte';
  import type { McpSetupDraft, McpSetupMode } from './mcp-endpoint-setup-state.svelte';
  import Button from '../shared/Button.svelte';
  import { parseConnectorCapability } from '#lib/admin/connector-capabilities.js';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '#lib/admin/downstream-mcp-connectors.js';
  import type { PromptCatalog, ResourceCatalog } from '#lib/admin/capability-catalogs.js';
  import type { InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
  import AdminShell from '#lib/components/admin/AdminShell.svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import ConnectorTabs from '#lib/components/admin/connectors/ConnectorTabs.svelte';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
  import { BrowserSelectionUrlAdapter } from '#lib/components/admin/shared/selection-url-port.js';
  import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
  import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceForm } from './downstream-mcp-workspace-state.svelte';

  let { data, form }: {
    data: {
      connectors: DownstreamMcpConnectorSummary[];
      selectedConnectorId?: string;
      selectedDetail?: DownstreamMcpConnector;
      selectedDetailFailed: boolean;
      catalog?: DownstreamMcpToolList;
      promptCatalog?: PromptCatalog;
      resourceCatalog?: ResourceCatalog;
      invocationPolicies?: InvocationPolicyTool[];
      accountIdentity?: HeaderAccountIdentityState;
    };
    form?: DownstreamMcpWorkspaceForm;
  } = $props();

  const toast = useToast();
  const initialSelectionId = untrack(() => (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? data.selectedDetail?.connector_id ?? data.connectors[0]?.connector_id);
  const state = new DownstreamMcpWorkspaceState(...untrack(() => [
    form?.mode,
    form?.values,
    data.selectedDetail?.connector_id !== initialSelectionId ? undefined : data.selectedDetail?.authorization_mode === 'personal'
      ? { mode: 'personal' as const, connector: data.selectedDetail }
      : data.selectedDetail && data.catalog && data.promptCatalog && data.resourceCatalog
        ? { mode: 'shared' as const, connector: data.selectedDetail, catalog: data.catalog, promptCatalog: data.promptCatalog, resourceCatalog: data.resourceCatalog, invocationPolicies: data.invocationPolicies ?? [] }
        : undefined,
    undefined,
    initialSelectionId,
    data.selectedConnectorId === initialSelectionId ? data.selectedDetailFailed : false,
    data.connectors,
    new BrowserSelectionUrlAdapter({
      readUrl: () => new URL((page.shallow?.url ?? page.url).href),
      replaceUrl: (url) => { void goto(url, { shallow: true, replace: true, state: {} }).catch(() => toast.error('Could not update connector URL')); }
    })
  ] as const));
  const api = adminApi();
  const registration = new PersonalServerFormState(api.personalServers, api.instanceConfiguration, null, api.personalServerDiscovery, async (id) => { state.close(); window.location.assign(`/admin/downstream-mcp-connectors?connector=${encodeURIComponent(id)}`); }, state.operations.loseAccess, state.operations.setRegistrationLocked);
  onMount(() => { if (initialSelectionId && initialSelectionId !== data.selectedConnectorId) state.selectConnector(initialSelectionId); void registration.reload(); return () => { registration.dispose(); state.personalSetup.dispose(); state.operations.dispose(); }; });
  function reloadRegistration(): void {
    if (registration.busy || registration.authenticationLost) return;
    if (registration.blocked) window.location.reload();
    else void registration.reload();
  }
  function closeRegistration(): void {
    if (registration.busy) return;
    registration.close();
    state.close();
  }
  function completeSetup(mode: McpSetupMode, draft: McpSetupDraft): void {
    if (mode !== 'personal') {
      state.completeSharedSetup(mode, draft);
      return;
    }
    const trigger = state.returnFocus;
    if (state.modal !== 'choose' || !trigger || state.operations.locked || !registration.canRegister) return;
    registration.openCreate();
    registration.setMetadata('name', draft.displayName);
    registration.setMetadata('description', draft.description);
    registration.setMetadata('endpoint', draft.endpointUrl);
    state.open('personal', trigger);
    if (draft.oauthMetadata) registration.discovery.acceptPreview(draft.oauthMetadata);
    else void registration.discovery.blur();
  }
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <SubpageContainer headingId="mcp-workspace-heading" title="MCP connectors" lede="Manage your MCP connections.">
    {#snippet actions()}
      <Button aria-label="Add MCP connector" disabled={state.operations.locked} onclick={(event) => state.beginCreate(event.currentTarget, form)}><span aria-hidden="true">+</span> Add MCP connector</Button>
    {/snippet}
    {#snippet navigation()}
      <ConnectorTabs activeTab="downstream-mcp" capability={parseConnectorCapability((page.shallow?.url ?? page.url).searchParams.get('capability'))} />
    {/snippet}
    {#if registration.blocked && state.modal !== 'personal'}
      <p role="alert">{registration.message} All workspace changes remain blocked until a full server reload.</p>
      <Button variant="secondary" disabled={registration.busy || registration.authenticationLost} onclick={reloadRegistration}>Reload servers</Button>
    {/if}
    {#if !state.operations.registrationLocked}
    <DownstreamMcpWorkspace connectors={data.connectors} selected={state.bundle?.connector} catalog={state.bundle?.catalog} promptCatalog={state.bundle?.promptCatalog} resourceCatalog={state.bundle?.resourceCatalog} invocationPolicies={state.bundle?.invocationPolicies ?? []} form={state.currentForm(form)} {state} />
    {/if}
  </SubpageContainer>
</AdminShell>

{#if state.modal === 'choose' && !state.operations.locked}
  <McpEndpointSetupWizard api={api.mcpEndpointSetup} personalAvailable={registration.canRegister} close={state.close} complete={completeSetup} accessLost={state.operations.loseAccess} />
{:else if state.modal === 'personal' && !state.operations.authenticationLost}
  <PersonalServerRegistration state={registration} close={closeRegistration} reload={reloadRegistration} />
{/if}
