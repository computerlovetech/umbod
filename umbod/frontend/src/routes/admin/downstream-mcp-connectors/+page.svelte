<script lang="ts">
  import { page } from '$app/state';
  import { operationState } from '#lib/admin/operations/operation-state.svelte.js';
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '#lib/admin/downstream-mcp-connectors.js';
  import type { PromptCatalog, ResourceCatalog } from '#lib/admin/capability-catalogs.js';
  import type { InvocationPolicyTool } from '#lib/admin/invocation-policy.js';
  import DownstreamMcpPageContent from '#lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte';
  import type { DownstreamMcpCreateValues } from '#lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte.js';
  import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';

  let { data }: {
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
  const form = $derived(operationState.forOwner({ route: page.url.pathname, connectorId: (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? data.connectors[0]?.connector_id }) as { status?: string; message?: string; mode?: string; values?: import('#lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte.js').DownstreamMcpCreateValues } | undefined);
</script>

<svelte:head><title>MCP connectors</title></svelte:head>

{#key data}
  <DownstreamMcpPageContent {data} {form} />
{/key}
