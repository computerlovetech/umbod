<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, lede, headingId, actions, navigation, children }: {
    title: string;
    lede: string;
    headingId?: string;
    actions?: Snippet;
    navigation: Snippet;
    children: Snippet;
  } = $props();
</script>

<div class="admin-page subpage-container">
  <header>
    <div>
      <h1 class="admin-title" id={headingId} tabindex="-1">{title}</h1>
      <p class="admin-lede">{lede}</p>
    </div>
    {#if actions}<div class="page-actions">{@render actions()}</div>{/if}
  </header>
  {@render navigation()}
  {@render children()}
</div>

<style>
  .subpage-container { min-width: 0; }
  header { align-items: flex-start; display: flex; gap: 24px; justify-content: space-between; margin-bottom: 32px; }
  .admin-lede { max-width: 48rem; }
  .page-actions { flex-shrink: 0; }
  @media (max-width: 1000px) { header { flex-wrap: wrap; gap: 16px; } }
</style>
