<script lang="ts" generics="Item extends { id: string; name: string; iconDataUrl?: string }">
  import { refreshAll } from '$app/navigation';
  import { page } from '$app/state';
  import type { Snippet } from 'svelte';
  import { connectorWorkspaceHref, portableConfigurationStatus, portableDuplicateReference, type UnifiedConnectorKind, type UnifiedConnectorRow } from '#lib/admin/unified-connectors.js';
  import { useToast } from '#lib/components/feedback/index.js';
  import LoadingButton from '#lib/components/admin/shared/LoadingButton.svelte';
  import { FormPendingState } from '#lib/components/admin/shared/form-pending-state.svelte.js';
  import AdminSplitWorkspace from '#lib/components/admin/shared/AdminSplitWorkspace.svelte';
  import ConnectorListEmptyState from './ConnectorListEmptyState.svelte';
  import ConnectorSidebarList from './ConnectorSidebarList.svelte';

  type Props = {
    kind: UnifiedConnectorKind;
    items: readonly Item[];
    unifiedRows?: readonly UnifiedConnectorRow[];
    unavailableKinds?: readonly UnifiedConnectorKind[];
    selectedId?: string;
    detailLabel: string;
    onselect: (item: Item) => void;
    metadata: Snippet<[Item]>;
    actions: Snippet<[Item]>;
    detail: Snippet;
  };

  let { kind, items, unifiedRows, unavailableKinds = [], selectedId, detailLabel, onselect, metadata, actions, detail }: Props = $props();

  const labels = { native: 'Native', openapi: 'OpenAPI', mcp: 'MCP', portable: 'Portable' } satisfies Record<UnifiedConnectorKind, string>;
  const capability = $derived((page.shallow?.url ?? page.url).searchParams.get('capability'));
  const linkedItems = $derived(unifiedRows?.filter((row) => row.kind !== kind).map((row) => {
    const reference = row.kind === 'portable' ? portableDuplicateReference(row, unifiedRows ?? []) : undefined;
    return {
      href: connectorWorkspaceHref(row, capability),
      name: row.name,
      iconDataUrl: row.iconDataUrl,
      badge: row.kind === 'portable' ? labels.portable : undefined,
      label: row.kind === 'portable'
        ? `${row.status} · ${portableConfigurationStatus(row.configured)}${reference ? ` · ${reference}` : ''}`
        : `${labels[row.kind]} · ${row.status}`
    };
  }));
  const count = $derived(items.length + (linkedItems?.length ?? 0));
  const unavailableLabels = $derived(unavailableKinds.map((unavailableKind) => labels[unavailableKind]).join(', '));
  const retry = new FormPendingState();
  const toast = useToast();

  async function retryInventory(): Promise<void> {
    if (retry.isPending('inventory')) return;
    retry.start('inventory');
    try {
      await refreshAll();
    } catch {
      toast.error('Could not reload connectors.');
    } finally {
      retry.stop('inventory');
    }
  }
</script>

{#if count === 0 && !unavailableLabels}
  <ConnectorListEmptyState {detailLabel} />
{:else}
  <AdminSplitWorkspace ariaLabel="Connectors workspace" sidebarLabel="Connectors" sidebarHeading="Connectors" {count} {detailLabel} {detail}>
    {#snippet sidebar()}
      {#if unavailableLabels}
        <div class="unavailable">
          <p role="status">Could not load connectors: {unavailableLabels}.</p>
          <LoadingButton label="Try again" loadingLabel="Reloading connectors" loading={retry.isPending('inventory')} variant="secondary" size="compact" onclick={retryInventory} />
        </div>
      {/if}
      <ConnectorSidebarList {items} {linkedItems} {selectedId} ariaLabel="Connectors" {onselect} {metadata} {actions} />
    {/snippet}
  </AdminSplitWorkspace>
{/if}

<style>
  .unavailable p { margin: 0 0 0.5rem; }
  .unavailable { color: var(--admin-muted); font-size: 0.8rem; margin: 0; padding: 0.75rem 1rem; }
</style>
