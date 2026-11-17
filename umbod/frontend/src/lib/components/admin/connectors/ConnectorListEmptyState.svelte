<script lang="ts">
  import AdminSplitWorkspace from '#lib/components/admin/shared/AdminSplitWorkspace.svelte';

  let {
    message,
    workspaceLabel = 'Connectors workspace',
    sidebarLabel = 'Connectors',
    sidebarHeading = 'Connectors',
    detailLabel = 'Selected connector detail'
  }: {
    message: string;
    workspaceLabel?: string;
    sidebarLabel?: string;
    sidebarHeading?: string;
    detailLabel?: string;
  } = $props();
</script>

<AdminSplitWorkspace ariaLabel={workspaceLabel} {sidebarLabel} {sidebarHeading} count={0} {detailLabel}>
  {#snippet sidebar()}
    <div class="connector-list-empty-state" role="img" aria-label={message}>
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="m19 5 3-3M2 22l3-3m1-7-3 3 6 6 3-3m6-6 3-3-6-6-3 3M5 13l6 6m2-14 6 6M8 8l2 2m4 4 2 2" />
      </svg>
    </div>
  {/snippet}
  {#snippet detail()}{/snippet}
</AdminSplitWorkspace>

<style>
  .connector-list-empty-state {
    align-items: center;
    color: var(--admin-muted);
    display: flex;
    flex: 1;
    justify-content: center;
    min-height: 180px;
    padding: 24px;
  }
</style>
