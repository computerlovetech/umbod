<script lang="ts">
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<div class="scrollable-tool-catalog" role="region" aria-label="Scrollable tool list">
  {@render children()}
</div>

<style>
  .scrollable-tool-catalog {
    max-height: min(62vh, 48rem);
    min-height: 0;
    overflow-y: auto;
    overscroll-behavior: contain;
    padding: 0.15rem 0.4rem 0.15rem 0.1rem;
    scrollbar-gutter: stable;
  }

  @media (max-width: 640px) {
    .scrollable-tool-catalog {
      max-height: 68vh;
    }
  }
</style>
