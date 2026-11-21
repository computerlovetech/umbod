<script lang="ts">
  import { page } from '$app/state';
  import { getAddConnector } from '#lib/components/admin/connectors/add-connector-state.svelte.js';
  import { operationState } from '#lib/admin/operations/operation-state.svelte.js';
  import DownstreamMcpPageContent from '#lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte';
  import type { DownstreamMcpWorkspaceForm } from '#lib/components/admin/downstream-mcp-connectors/downstream-mcp-workspace-state.svelte.js';
  import type { PageData } from './$types';

  let { data }: { data: PageData } = $props();
  const addConnector = getAddConnector();
  const form = $derived(operationState.forOwner({ route: page.url.pathname, connectorId: (page.shallow?.url ?? page.url).searchParams.get('connector') ?? data.selectedConnectorId ?? data.connectors[0]?.connector_id }) as DownstreamMcpWorkspaceForm | undefined);
</script>

{#key data}
  <DownstreamMcpPageContent {data} {form} {addConnector} />
{/key}
