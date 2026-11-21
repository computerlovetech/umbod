<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { useToast } from '#lib/components/feedback/index.js';
  import { onMount, untrack } from 'svelte';
  import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
  import { PersonalServerFormState } from '../personal-mcp-servers/personal-server-form-state.svelte';
  import PersonalServerRegistration from '../personal-mcp-servers/PersonalServerRegistration.svelte';
  import McpEndpointSetupWizard from './McpEndpointSetupWizard.svelte';
  import { McpEndpointSetupState, type McpSetupDraft, type McpSetupMode } from './mcp-endpoint-setup-state.svelte';
  import Button from '../shared/Button.svelte';
  import type { UnifiedConnectorInventory } from '#lib/admin/unified-connectors.js';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '#lib/admin/downstream-mcp-connectors.js';
  import type { PromptCatalog, ResourceCatalog } from '#lib/admin/capability-catalogs.js';
  import type { InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
  import type { AddConnectorState } from '../connectors/add-connector-state.svelte.js';
  import { BrowserSelectionUrlAdapter } from '#lib/components/admin/shared/selection-url-port.js';
  import DownstreamMcpWorkspace from './DownstreamMcpWorkspace.svelte';
  import { DownstreamMcpWorkspaceState, type DownstreamMcpWorkspaceForm } from './downstream-mcp-workspace-state.svelte';

  let { data, form, addConnector }: {
    addConnector: AddConnectorState;
    data: Partial<UnifiedConnectorInventory> & {
      connectors: DownstreamMcpConnectorSummary[];
      selectedConnectorId?: string;
      selectedDetail?: DownstreamMcpConnector;
      selectedDetailFailed: boolean;
      catalog?: DownstreamMcpToolList;
      promptCatalog?: PromptCatalog;
      resourceCatalog?: ResourceCatalog;
      invocationPolicies?: InvocationPolicyTool[];
    };
    form?: DownstreamMcpWorkspaceForm;
  } = $props();

  const toast = useToast();
  const initialSelectionId = untrack(() => (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? data.selectedDetail?.connector_id ?? data.connectors[0]?.connector_id);
  const workspace = new DownstreamMcpWorkspaceState(...untrack(() => [
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
  const registration = new PersonalServerFormState(api.personalServers, api.instanceConfiguration, null, api.personalServerDiscovery, async (id) => { workspace.close(); window.location.assign(`/admin/downstream-mcp-connectors?connector=${encodeURIComponent(id)}`); }, workspace.operations.loseAccess, workspace.operations.setRegistrationLocked);
  let setup = $state.raw<McpEndpointSetupState>();
  onMount(() => { if (initialSelectionId && initialSelectionId !== data.selectedConnectorId) workspace.selectConnector(initialSelectionId); void registration.reload(); return () => { setup?.dispose(); registration.dispose(); workspace.personalSetup.dispose(); workspace.operations.dispose(); }; });
  onMount(() => addConnector.registerSetup({
    kind: 'mcp',
    nativeAvailable: () => data.nativeAvailable ?? false,
    nativeUnavailable: () => data.unavailableKinds?.includes('native') ?? false,
    disabled: () => workspace.operations.locked,
    create: beginSetup
  }));
  function beginSetup(trigger: HTMLElement): void {
    if (workspace.operations.locked) return;
    setup?.dispose();
    setup = new McpEndpointSetupState({
      api: () => api.mcpEndpointSetup,
      personalAvailable: () => registration.canRegister,
      complete: completeSetup,
      accessLost: workspace.operations.loseAccess
    });
    workspace.beginCreate(trigger, form);
  }
  function backFromPersonalSetup(): void {
    if (registration.busy || workspace.operations.locked) return;
    registration.close();
    workspace.returnToAccess();
  }
  function reloadRegistration(): void {
    if (registration.busy || registration.authenticationLost) return;
    if (registration.blocked) window.location.reload();
    else void registration.reload();
  }
  function closeRegistration(): void {
    if (registration.busy) return;
    registration.close();
    workspace.close();
  }
  function completeSetup(mode: McpSetupMode, draft: McpSetupDraft): void {
    if (mode !== 'personal') {
      workspace.completeSharedSetup(mode, draft);
      return;
    }
    const trigger = workspace.returnFocus;
    if (workspace.modal !== 'choose' || !trigger || workspace.operations.locked || !registration.canRegister) return;
    registration.openCreate();
    registration.setMetadata('name', draft.displayName);
    registration.setMetadata('description', draft.description);
    registration.setMetadata('endpoint', draft.endpointUrl);
    workspace.open('personal', trigger);
    if (draft.oauthMetadata) registration.discovery.acceptPreview(draft.oauthMetadata);
    else void registration.discovery.blur();
  }
</script>

{#if registration.blocked && workspace.modal !== 'personal'}
  <p role="alert">{registration.message} All workspace changes remain blocked until a full server reload.</p>
  <Button variant="secondary" disabled={registration.busy || registration.authenticationLost} onclick={reloadRegistration}>Reload servers</Button>
{/if}
{#if !workspace.operations.registrationLocked}
<DownstreamMcpWorkspace connectors={data.connectors} unifiedRows={data.unifiedRows} unavailableKinds={data.unavailableKinds} selected={workspace.bundle?.connector} catalog={workspace.bundle?.catalog} promptCatalog={workspace.bundle?.promptCatalog} resourceCatalog={workspace.bundle?.resourceCatalog} invocationPolicies={workspace.bundle?.invocationPolicies ?? []} form={workspace.currentForm(form)} state={workspace} />
{/if}

{#if workspace.modal === 'choose' && setup && !workspace.operations.locked}
  <McpEndpointSetupWizard state={setup} close={workspace.close} onbacktotype={() => addConnector.reopen('mcp')} />
{:else if workspace.modal === 'personal' && !workspace.operations.authenticationLost}
  <PersonalServerRegistration state={registration} close={closeRegistration} reload={reloadRegistration} onback={setup ? backFromPersonalSetup : undefined} />
{/if}
