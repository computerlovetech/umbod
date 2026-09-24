<script lang="ts">
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<ul class="tool-list capability-grid">
  {@render children()}
</ul>

<style>
  .capability-grid {
    align-items: start;
    display: grid;
    gap: 0.875rem;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
    list-style: none;
    margin: 0;
    padding: 0;
  }
</style>
