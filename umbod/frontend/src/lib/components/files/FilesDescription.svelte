<script lang="ts">
  import type { DescriptionState } from '$lib/files/state/description-state.svelte';
  let { state }: { state: DescriptionState } = $props();
</script>

<section aria-label="Description">
  <h2>Description</h2>
  {#if state.description}<p class="description">{state.description}</p>{:else}<p>No description.</p>{/if}
</section>

<style>
  section { margin: 1rem 0; }
  h2 { font-size: 1rem; }
  p { color: var(--admin-muted); }
  .description { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
