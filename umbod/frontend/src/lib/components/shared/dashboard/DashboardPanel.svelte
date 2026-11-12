<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, metadata, actions, children }: { title: string; metadata?: string; actions?: Snippet; children: Snippet } = $props();
</script>

<section class="dashboard-panel" aria-label={title}>
  <header>
    <h3>{title}</h3>
    {#if metadata}<span class="metadata">{metadata}</span>{/if}
  </header>
  {#if actions}<div class="panel-actions">{@render actions()}</div>{/if}
  <div class="panel-content">{@render children()}</div>
</section>

<style>
  .dashboard-panel { box-sizing: border-box; flex: 1; min-width: 0; border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); background: var(--admin-panel); padding: 20px; }
  header { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 20px; }
  h3 { margin: 0; color: var(--admin-ink); font-size: 14px; font-weight: 600; line-height: 1.4; letter-spacing: -.015em; }
  .metadata { color: var(--admin-muted); font-size: 12px; line-height: 1.4; }
  .panel-actions { margin-bottom: 16px; }
  .panel-content { min-width: 0; }
</style>
