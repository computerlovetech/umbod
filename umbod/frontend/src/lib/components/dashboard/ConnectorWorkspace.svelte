<script lang="ts">
  import type { DashboardController } from '$lib/dashboard/state/port';
  import type { CatalogueConnector } from '$lib/dashboard/domain/schemas';
  import { catalogueSidebarItem, connectorKindLabels } from '$lib/dashboard/presentation';
  import AdminSplitWorkspace from '$lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import ConnectorSidebarList from '$lib/components/admin/connectors/ConnectorSidebarList.svelte';
  import ConnectionCard from '$lib/components/personal-connections/ConnectionCard.svelte';
  import ConnectionActions from '$lib/components/personal-connections/ConnectionActions.svelte';
  import ConnectionStatusBadge from '$lib/components/personal-connections/ConnectionStatusBadge.svelte';
  import { personalAccessStatus } from '$lib/personal-connections/presentation';
  import ConnectorDetail from './ConnectorDetail.svelte';

  let { state, canManage = false }: { state: DashboardController; canManage?: boolean } = $props();

  function managementHref(connector: CatalogueConnector): string | undefined {
    if (!canManage) return undefined;
    const paths = { native: '/admin/connectors', openapi: '/admin/openapi-connectors', downstream_mcp: '/admin/downstream-mcp-connectors' };
    return `${paths[connector.kind]}?connector=${encodeURIComponent(connector.connector_id)}`;
  }
</script>

<AdminSplitWorkspace ariaLabel="Your connector workspace" sidebarLabel="Available connectors" sidebarHeading="Connectors" count={state.connectors.length} detailLabel="Selected connector">
  {#snippet sidebar()}
    {#key state.identityKey}
    <ConnectorSidebarList items={state.connectors.map(catalogueSidebarItem)} selectedId={state.selectedId} ariaLabel="Your connectors" onselect={(item) => state.selectConnector(item.id)}>
      {#snippet metadata(item)}
        <span class="connector-meta">{connectorKindLabels[item.kind]} · {item.ownership === 'personal' ? 'Personal authorization' : 'Shared authorization'}</span>
        <span class="managed-label">Organisation-managed</span>
        {#if item.ownership === 'personal'}
          {@const card = state.personalCard(item.connector_id)}
          {#if card}<ConnectionStatusBadge status={personalAccessStatus(card)} compact />{/if}
        {/if}
      {/snippet}
      {#snippet actions(item)}
        {#if item.ownership === 'personal'}
          {@const card = state.personalCard(item.connector_id)}
          {#if card}<ConnectionActions state={card} onaction={() => state.selectConnector(item.id)} />{/if}
        {/if}
      {/snippet}
    </ConnectorSidebarList>
    {/key}
  {/snippet}
  {#snippet detail()}
    {#if state.selectedConnector}
      {@const connector = state.selectedConnector}
      {#key state.identityKey + ':' + state.selectedId}
        {#snippet personalActions()}
          {@const card = state.personalCard(connector.connector_id)}
          {#if card}
            <ConnectionCard state={card} embedded />
          {:else}
            <p role="status">{state.personalPhase === 'loading' ? 'Loading personal access…' : 'Personal access unavailable'}</p>
          {/if}
        {/snippet}
        <ConnectorDetail {connector} manageHref={managementHref(connector)} children={connector.ownership === 'personal' ? personalActions : undefined} />
      {/key}
    {/if}
  {/snippet}
</AdminSplitWorkspace>

<style>
  .managed-label { color: var(--admin-muted); font-size: 0.65rem; font-weight: 600; width: fit-content; }
  p { color: var(--admin-muted); font-size: 0.85rem; line-height: 1.6; }
</style>
