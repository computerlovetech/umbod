<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import type { NodeSummary } from '$lib/files/domain/schemas';
  import type { SharingEligibilityState } from '$lib/files/state/sharing-eligibility-state.svelte';
  let { node, sharing }: { node: NodeSummary; sharing: SharingEligibilityState } = $props();
</script>

{#if sharing.available(node.id)}
  <Button variant="secondary" style="position: relative; z-index: 1; gap: 0.5rem;" type="button" aria-label={`Share “${sharing.label(node)}”`} title={`Share “${sharing.label(node)}”`} onclick={(event) => { void sharing.dialog.show(node, event.currentTarget); }}>
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" /></svg>
    <span>Share</span>
  </Button>
{/if}
