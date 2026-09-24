<script lang="ts">
  import type { DownstreamMcpConnector, DownstreamMcpConnectorSummary, DownstreamMcpToolList } from '$lib/admin/downstream-mcp-connectors';
  import type { PromptCatalog, ResourceCatalog } from '$lib/admin/capability-catalogs';
  import type { InvocationPolicyTool } from '$lib/admin/invocation-policy';
  import DownstreamMcpPageContent from '$lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte';
  import type { DownstreamMcpCreateValues } from '$lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte';
  import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

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
</script>

<svelte:head><title>MCP proxy connectors</title></svelte:head>

{#key data}
  <DownstreamMcpPageContent {data} {form} />
{/key}
