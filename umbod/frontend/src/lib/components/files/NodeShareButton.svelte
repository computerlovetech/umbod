<script lang="ts">
  import type { NodeSummary } from '$lib/files/domain/schemas';
  import type { SharingEligibilityState } from '$lib/files/state/sharing-eligibility-state.svelte';
  let { node, sharing, compact = false }: { node: NodeSummary; sharing: SharingEligibilityState; compact?: boolean } = $props();
</script>

{#if sharing.available(node.id)}
  <button type="button" class={{ compact }} aria-label={`Share “${node.name || 'Files'}”`} title={`Share “${node.name || 'Files'}”`} onclick={(event) => { void sharing.dialog.show(node, event.currentTarget); }}>
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" /></svg>
    {#if !compact}<span>Share</span>{/if}
  </button>
{/if}

<style>
  button { position: relative; z-index: 1; display: inline-flex; align-items: center; justify-content: center; gap: 0.5rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; padding: 0.6rem 0.9rem; cursor: pointer; }
  button.compact { width: 2.75rem; height: 2.75rem; padding: 0; border: 0; background: transparent; color: var(--admin-accent); }
  button:hover { background: var(--admin-soft); }
  button:focus-visible { outline: 2px solid var(--admin-accent); outline-offset: 3px; }
</style>
