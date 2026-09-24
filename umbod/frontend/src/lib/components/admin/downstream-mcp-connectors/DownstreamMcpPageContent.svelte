<script lang="ts">
  import { replaceState } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
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
    data.selectedDetail && data.catalog && data.promptCatalog && data.resourceCatalog
      ? { connector: data.selectedDetail, catalog: data.catalog, promptCatalog: data.promptCatalog, resourceCatalog: data.resourceCatalog, invocationPolicies: data.invocationPolicies ?? [] }
      : undefined,
    undefined,
    data.selectedConnectorId,
    data.selectedDetailFailed,
    data.connectors,
    new BrowserSelectionUrlAdapter({ readUrl: () => page.url, replaceUrl: (url) => replaceState(url, {}) })
  ] as const));
  const fallbackAccountIdentity: HeaderAccountIdentityState = { kind: 'hidden' };
</script>

<AdminShell activeItem="connectors" accountIdentity={data.accountIdentity ?? fallbackAccountIdentity} contentWidth="wide">
  <div class="admin-page">
    <ConnectorPageHeader title="MCP proxy connectors" lede="Connect downstream MCP servers, discover their tools, and control what is available through public proxy endpoints." addLabel="Add MCP proxy connector" onadd={(trigger) => state.open('create', trigger)} />
    <ConnectorTabs activeTab="downstream-mcp" capability={parseConnectorCapability(page.url.searchParams.get('capability'))} />
    <DownstreamMcpWorkspace connectors={data.connectors} selected={state.bundle?.connector} catalog={state.bundle?.catalog} promptCatalog={state.bundle?.promptCatalog} resourceCatalog={state.bundle?.resourceCatalog} invocationPolicies={state.bundle?.invocationPolicies ?? []} {form} {state} />
  </div>
</AdminShell>

<style>
  @media (max-width: 600px) {
    .admin-page { min-width: 0; overflow: hidden; }
  }
</style>
