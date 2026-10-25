<script lang="ts">
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '$lib/admin/infrastructure/admin-api';
  import { PersonalServerFormState } from '../personal-mcp-servers/personal-server-form-state.svelte';
  import PersonalServerRegistration from '../personal-mcp-servers/PersonalServerRegistration.svelte';
  import PersonalServerDialog from '../personal-mcp-servers/PersonalServerDialog.svelte';
  import Button from '../shared/Button.svelte';
  import { parseConnectorCapability } from '$lib/admin/connector-capabilities';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '$lib/admin/downstream-mcp-connectors';
  import type { PromptCatalog, ResourceCatalog } from '$lib/admin/capability-catalogs';
  import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import AdminShell from '$lib/components/admin/AdminShell.svelte';
  import ConnectorPageHeader from '$lib/components/admin/connectors/ConnectorPageHeader.svelte';
  import ConnectorTabs from '$lib/components/admin/connectors/ConnectorTabs.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
  import { BrowserSelectionUrlAdapter } from '$lib/components/admin/shared/selection-url-port';
  import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
  import { DownstreamMcpWorkspaceState, type DownstreamMcpCreateValues } from './downstream-mcp-workspace-state.svelte';

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
    form?: {
      message?: string;
      status?: string;
      mode?: string;
      values?: DownstreamMcpCreateValues;
    };
  } = $props();

  const state = new DownstreamMcpWorkspaceState(...untrack(() => [
    form?.mode,
    form?.values,
    data.selectedDetail?.authorization_mode === 'personal'
      ? { mode: 'personal' as const, connector: data.selectedDetail }
      : data.selectedDetail && data.catalog && data.promptCatalog && data.resourceCatalog
        ? { mode: 'shared' as const, connector: data.selectedDetail, catalog: data.catalog, promptCatalog: data.promptCatalog, resourceCatalog: data.resourceCatalog, invocationPolicies: data.invocationPolicies ?? [] }
        : undefined,
    undefined,
    data.selectedConnectorId,
    data.selectedDetailFailed,
    data.connectors,
    new BrowserSelectionUrlAdapter({ readUrl: () => page.url, replaceUrl: (url) => replaceState(url, {}) })
  ] as const));
  const api = adminApi();
  const registration = new PersonalServerFormState(api.personalServers, api.instanceConfiguration, null, async (id) => { state.close(); window.location.assign(`/admin/downstream-mcp-connectors?connector=${encodeURIComponent(id)}`); }, state.operations.loseAccess, state.operations.setRegistrationLocked);
  onMount(() => { void registration.reload(); return () => { registration.dispose(); state.operations.dispose(); }; });
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
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <div class="admin-page">
    <ConnectorPageHeader headingId="mcp-workspace-heading" title="MCP connectors" lede="Manage your MCP connections." addLabel="Add MCP connector" disabled={state.operations.locked} onadd={(trigger) => state.beginCreate(registration.availability, trigger)} />

    <ConnectorTabs activeTab="downstream-mcp" capability={parseConnectorCapability(page.url.searchParams.get('capability'))} />
    {#if registration.blocked && state.modal !== 'personal'}
      <p role="alert">{registration.message} All workspace changes remain blocked until a full server reload.</p>
      <Button variant="secondary" disabled={registration.busy || registration.authenticationLost} onclick={reloadRegistration}>Reload servers</Button>
    {/if}
    {#if !state.operations.registrationLocked}
    <DownstreamMcpWorkspace connectors={data.connectors} selected={state.bundle?.connector} catalog={state.bundle?.catalog} promptCatalog={state.bundle?.promptCatalog} resourceCatalog={state.bundle?.resourceCatalog} invocationPolicies={state.bundle?.invocationPolicies ?? []} {form} {state} />
    {/if}
  </div>
</AdminShell>

{#if state.modal === 'choose' && !state.operations.locked}
  <PersonalServerDialog title="Add MCP connector" titleId="mcp-mode-title" descriptionId="mcp-mode-description" close={state.close}>
    <p id="mcp-mode-description">Use shared credentials or let each user connect their own account.</p>
    <Button onclick={() => state.open('create', state.returnFocus!)}>Shared</Button>
    <Button disabled={!registration.canRegister} onclick={() => { registration.openCreate(); state.open('personal', state.returnFocus!); }}>Personal</Button>
    {#if registration.message}<p role="alert">{registration.message}</p>{/if}
  </PersonalServerDialog>
{:else if state.modal === 'personal' && !state.operations.authenticationLost}
  <PersonalServerRegistration state={registration} close={closeRegistration} reload={reloadRegistration} />
{/if}

<style>
  @media (max-width: 600px) {
    .admin-page { min-width: 0; overflow: hidden; }
  }
</style>
