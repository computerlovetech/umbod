<script lang="ts">
  import type { Snippet } from 'svelte';

  let { identity, navigation, sharing, actions, description, children }: {
    identity: Snippet;
    navigation: Snippet;
    sharing: Snippet;
    actions: Snippet;
    description: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="files-container">
  <header class="heading-identity">{@render identity()}</header>
  <div class="location-bar">
    <div class="navigation">{@render navigation()}</div>
    <div class="toolbar" role="group" aria-label="Location actions">
      <div class="sharing">{@render sharing()}</div>
      <div class="actions">{@render actions()}</div>
    </div>
  </div>
  {@render description()}
  <div class="content">{@render children()}</div>
</div>

<style>
  .files-container { min-width: 0; }
  .heading-identity { min-height: 2.75rem; display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 1rem; }
  .location-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.75rem 1rem; margin: 1rem 0; }
  .navigation { flex: 1 1 12rem; min-width: 0; min-height: 2.75rem; }
  .toolbar { display: flex; align-items: stretch; justify-content: flex-end; gap: 0.6rem; min-height: 2.5rem; margin-left: auto; }
  .sharing, .actions { display: flex; flex-wrap: wrap; align-items: stretch; gap: 0.6rem; }
  .actions { justify-content: flex-end; }
  .content { min-width: 0; margin-top: 1.5rem; }
</style>
