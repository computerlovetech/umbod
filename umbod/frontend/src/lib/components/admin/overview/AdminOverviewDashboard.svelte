<script lang="ts">
  import AdminStatCard from '$lib/components/admin/shared/AdminStatCard.svelte';
  import type { AdminOverview, Available, ConnectorKind } from '$lib/admin/overview/models';

  let { overview }: { overview: AdminOverview } = $props();

  const families: Record<ConnectorKind, { label: string; href: string }> = {
    catalog: { label: 'Catalog', href: '/admin/connectors' },
    openapi: { label: 'OpenAPI', href: '/admin/openapi-connectors' },
    mcp: { label: 'MCP proxies', href: '/admin/downstream-mcp-connectors' }
  };
  const attentionLabels = {
    unconfigured: 'Unconfigured connectors',
    draft: 'Draft connectors',
    unpublished: 'Unpublished connectors',
    unhealthy: 'Unhealthy MCP discovery'
  };
  const attentionItems = $derived(overview.attention.status === 'available'
    ? Object.entries(overview.attention.value).filter(([, count]) => count > 0)
    : []);

  function countText(count: Available<number>): string {
    return count.status === 'available' ? String(count.value) : 'Unavailable';
  }
</script>

<div class="admin-page">
  <p class="admin-eyebrow">Umbod</p>
  <h1 class="admin-title">Overview</h1>
  <p class="admin-lede">Connector configuration, tool activation and publication at a glance.</p>

  <dl class="stats">
    <AdminStatCard label="Configured connectors">
      <strong>{countText(overview.configured)}</strong>
      <p>Configured catalog and OpenAPI connectors, including saved MCP proxies.</p>
    </AdminStatCard>
    <AdminStatCard label="Enabled / known tools">
      <strong>{overview.tools.status === 'available' ? `${overview.tools.value.enabled} / ${overview.tools.value.known}` : 'Unavailable'}</strong>
      <p>Tool activations across all listed connectors.</p>
    </AdminStatCard>
    <AdminStatCard label="Published connectors">
      <strong>{countText(overview.published)}</strong>
      <p>Published catalog, OpenAPI and MCP connectors.</p>
    </AdminStatCard>
    <AdminStatCard label="Registered permission groups">
      <strong>{countText(overview.permissionGroups)}</strong>
      <p><a href="/admin/group-permissions">Manage group permissions</a></p>
    </AdminStatCard>
  </dl>

  <section class="panel" aria-labelledby="breakdown-title">
    <h2 id="breakdown-title">Connector breakdown</h2>
    <div class="table-scroll" role="region" aria-labelledby="breakdown-title" tabindex="0">
      <table aria-labelledby="breakdown-title">
        <thead><tr><th scope="col">Type</th><th scope="col">Configured / saved</th><th scope="col">Published</th><th scope="col">Enabled / known tools</th></tr></thead>
        <tbody>
          {#each overview.breakdown as row (row.kind)}
            <tr>
              <th scope="row"><a href={families[row.kind].href}>{families[row.kind].label}</a></th>
              <td>{row.connectors.status === 'available' ? row.connectors.value.configured : 'Unavailable'}</td>
              <td>{row.connectors.status === 'available' ? row.connectors.value.published : 'Unavailable'}</td>
              <td>{row.tools.status === 'available' ? `${row.tools.value.enabled} / ${row.tools.value.known}` : 'Unavailable'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </section>

  {#if overview.breakdown.some((row) => row.connectors.status === 'unavailable' || row.tools.status === 'unavailable') || overview.permissionGroups.status === 'unavailable'}
    <p class="warning" role="status">Some dashboard data could not be loaded. Unavailable counts are not zero; other counts remain visible.</p>
  {/if}

  {#if overview.attention.status === 'unavailable' || attentionItems.length > 0}
    <section class="panel" aria-labelledby="attention-title">
      <h2 id="attention-title">Needs attention</h2>
      {#if overview.attention.status === 'unavailable'}
        <p class="warning" role="status">Connector attention counts are unavailable. Configuration, publication and MCP discovery could not be fully assessed.</p>
      {:else}
        <ul>
          {#each attentionItems as [key, count] (key)}
            <li><span>{attentionLabels[key as keyof typeof attentionLabels]}</span><strong>{count}</strong></li>
          {/each}
        </ul>
        <p>Configuration and publication states are not service errors. Unknown MCP discovery is not counted as unhealthy.</p>
      {/if}
    </section>
  {/if}
</div>

<style>
  .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 1rem; margin: 2rem 0; }
  strong { font-size: 1.4rem; font-weight: 600; }
  .panel { min-width: 0; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1.25rem; margin-top: 1.5rem; }
  h2 { font-size: 1rem; margin: 0 0 1rem; }
  a { color: var(--admin-accent); text-underline-offset: 0.2em; }
  a:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
  .table-scroll { overflow-x: auto; max-width: 100%; }
  table { border-collapse: collapse; width: 100%; text-align: left; font-size: 0.9rem; }
  th, td { padding: 0.8rem; border-bottom: 1px solid var(--admin-border); }
  thead th { color: var(--admin-muted); font-size: 0.8rem; font-weight: 500; }
  tbody tr:last-child th, tbody tr:last-child td { border-bottom: none; }
  .warning { color: var(--admin-warning-text); background: var(--admin-warning-bg); border: 1px solid var(--admin-warning-border); padding: 0.9rem; border-radius: var(--admin-radius); }
  ul { list-style: none; padding: 0; margin: 0; }
  li { display: flex; justify-content: space-between; gap: 1rem; padding: 0.65rem 0; border-bottom: 1px solid var(--admin-border); }
  li strong { font-size: 1rem; }
  .panel p { color: var(--admin-muted); font-size: 0.85rem; line-height: 1.5; }
  .panel p.warning { color: var(--admin-warning-text); }
  @media (max-width: 1100px) { .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 600px) { .stats { grid-template-columns: minmax(0, 1fr); } .panel { padding: 1rem; } th, td { padding: 0.65rem; } }
</style>
