<script lang="ts">
  import type { Snippet } from 'svelte';
  import type { CatalogueConnector } from '$lib/dashboard/domain/schemas';
  import { connectorKindLabels } from '$lib/dashboard/presentation';
  import ConnectorDetailSummary from '$lib/components/admin/connectors/ConnectorDetailSummary.svelte';
  import ConnectorDetailItem from '$lib/components/admin/connectors/ConnectorDetailItem.svelte';
  import CatalogueCapabilities from './CatalogueCapabilities.svelte';

  let { connector, children: personalActions, manageHref }: { connector: CatalogueConnector; children?: Snippet; manageHref?: string } = $props();
  const headingId = $props.id();
</script>

<ConnectorDetailSummary {headingId} title={connector.display_name}>
  {#snippet description()}
    <p>{connector.capability_description}</p>
  {/snippet}
  {#snippet summary()}
    <ConnectorDetailItem label="Connector type">{connectorKindLabels[connector.kind]}</ConnectorDetailItem>
    <ConnectorDetailItem label="Authorization">{connector.ownership === 'personal' ? 'Personal' : 'Shared'}</ConnectorDetailItem>
    <ConnectorDetailItem label="Capabilities">{connector.capabilities.length} available</ConnectorDetailItem>
  {/snippet}
  {#snippet children()}
    <div class="managed-notice">
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /><path d="M12 14v3" /></svg>
      <div>
        <h3>Organisation-managed</h3>
        <p>Your organisation controls connector settings and available capabilities.</p>
        {#if connector.ownership === 'personal'}<p>You authorize access using your own account.</p>{/if}
        {#if manageHref}<a href={manageHref}>Manage in Connectors <span aria-hidden="true">→</span></a>{/if}
      </div>
    </div>
    {#if personalActions}
      <div class="personal-connection">{@render personalActions()}</div>
    {/if}
    <CatalogueCapabilities capabilities={connector.capabilities} />
  {/snippet}
</ConnectorDetailSummary>

<style>
  .managed-notice { align-items: flex-start; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); display: flex; gap: 0.75rem; padding: 1rem; }
  svg { color: var(--admin-muted); flex: 0 0 auto; height: 1.15rem; margin-top: 0.1rem; width: 1.15rem; }
  h3 { color: var(--admin-ink); font-size: 0.85rem; margin: 0; }
  .managed-notice p { color: var(--admin-muted); font-size: 0.8rem; line-height: 1.6; margin: 0.35rem 0 0; }
  a { color: var(--admin-accent); display: inline-block; font-size: 0.8rem; font-weight: 600; margin-top: 0.65rem; text-underline-offset: 3px; }
  a:focus-visible { outline: 3px solid var(--admin-focus); outline-offset: 3px; }
  .personal-connection { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); margin-top: 1rem; padding: 0 1rem 1rem; }
</style>
