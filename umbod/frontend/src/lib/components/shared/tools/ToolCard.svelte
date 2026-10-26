<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, name, description, parameters, outputSchema, controls }: {
    title: string;
    name: string;
    description?: Snippet;
    parameters?: Snippet;
    outputSchema?: Snippet;
    controls?: Snippet;
  } = $props();
</script>

<article class="tool-card">
  <div class="tool-heading">
    <div class="tool-title">
      <h4 title={title}>{title}</h4>
      <code>{name}</code>
    </div>
    {#if controls}{@render controls()}{/if}
  </div>
  {@render description?.()}
  {@render parameters?.()}
  {@render outputSchema?.()}
</article>

<style>
  .tool-card { min-width: 0; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1rem; }
  .tool-heading { align-items: flex-start; display: flex; flex-wrap: wrap; gap: 0.75rem; justify-content: space-between; }
  .tool-title { align-items: flex-start; display: flex; flex: 1 1 20rem; flex-direction: column; gap: 0.5rem; min-width: 0; }
  h4 { color: var(--admin-ink); display: -webkit-box; font-size: 0.94rem; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; margin: 0; max-width: 100%; overflow: hidden; overflow-wrap: anywhere; }
  code { background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 4px; font-family: var(--admin-mono); font-size: 0.75rem; line-height: 1.4; max-width: 100%; overflow-wrap: anywhere; padding: 0.2rem 0.4rem; white-space: normal; word-break: break-word; }
</style>
