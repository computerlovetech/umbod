<script lang="ts">
  import type { Snippet } from 'svelte';

  let { identity, actions, children }: {
    identity: Snippet;
    actions?: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="page-container">
  <header class="page-container-heading">
    <div class="page-container-identity">{@render identity()}</div>
    {#if actions}
      <div class="page-container-actions">{@render actions()}</div>
    {/if}
  </header>
  <div class="page-container-content">{@render children()}</div>
</div>

<style>
  .page-container { min-width: 0; }
  .page-container-heading { min-height: 2.75rem; display: flex; flex-wrap: wrap; align-items: flex-start; gap: 1rem; }
  .page-container-identity { flex: 1 1 12rem; min-width: 0; }
  .page-container-actions { display: flex; align-items: center; justify-content: flex-end; flex-wrap: wrap; gap: 0.6rem; min-height: 2.5rem; margin-left: auto; }
  .page-container-content { min-width: 0; margin-top: 1.75rem; }
</style>
