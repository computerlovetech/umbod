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
    <ConnectorPageHeader headingId="mcp-workspace-heading" title="MCP connectors" lede="Manage shared MCP proxies and personal server allowlist definitions in one workspace." addLabel="Add MCP connector" disabled={state.operations.locked} onadd={(trigger) => { if (!state.operations.locked) state.open('choose', trigger); }} />

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
    <p id="mcp-mode-description">Shared connectors use shared credentials and catalogues. Personal servers use each user's own authorization and private discovery.</p>
    <Button onclick={() => state.open('create', state.returnFocus!)}>Shared</Button>
    <Button disabled={!registration.canRegister} onclick={() => { registration.openCreate(); state.open('personal', state.returnFocus!); }}>Personal</Button>
    {#if registration.availability.registration !== 'enabled'}
      <p>Personal connections are {registration.availability.registration}. An operator must enable personal connections and configure a stable identity namespace. Startup settings are read-only.</p>
    {/if}
    {#if registration.availability.registration === 'enabled' && registration.availability.authorization !== 'enabled'}
      <p>User OAuth availability is {registration.availability.authorization}. Registration remains available but does not authorize users or permit execution.</p>
    {/if}
    {#if registration.message}<p role="alert">{registration.message}</p>{/if}
    <a href="/admin/instance-configuration">View startup settings (read-only)</a>
    <Button variant="secondary" disabled={registration.busy || registration.loading || registration.authenticationLost} onclick={reloadRegistration}>{registration.blocked ? 'Reload servers' : 'Reload availability'}</Button>
  </PersonalServerDialog>
{:else if state.modal === 'personal' && !state.operations.authenticationLost}
  <PersonalServerRegistration state={registration} close={closeRegistration} reload={reloadRegistration} />
{/if}

<style>
  @media (max-width: 600px) {
    .admin-page { min-width: 0; overflow: hidden; }
  }
</style>
