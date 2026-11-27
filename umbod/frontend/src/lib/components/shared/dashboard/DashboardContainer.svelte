<script lang="ts">
  import type { Snippet } from 'svelte';

  let { title, showTitle = true, actions, children, footer }: {
    title: string;
    showTitle?: boolean;
    actions?: Snippet;
    children: Snippet;
    footer?: Snippet;
  } = $props();
</script>

<section class="dashboard-container" aria-label={title}>
  <header class={['dashboard-heading', !showTitle && 'dashboard-heading-actions-only']}>
    <h2 class={!showTitle ? 'visually-hidden' : undefined}>{title}</h2>
    {#if actions}<div class="dashboard-actions">{@render actions()}</div>{/if}
  </header>
  <div class="dashboard-content">{@render children()}</div>
  {#if footer}<footer>{@render footer()}</footer>{/if}
</section>

<style>
  .dashboard-container { container: dashboard-layout / inline-size; min-width: 0; color: var(--admin-ink); }
  .dashboard-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 20px; }
  .dashboard-heading-actions-only .dashboard-actions { flex: 1; min-width: 0; }
  .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  h2 { font-size: 17px; font-weight: 600; letter-spacing: -.025em; line-height: 1.4; margin: 0; }
  .dashboard-actions { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
  .dashboard-content { display: flex; flex-direction: column; gap: 20px; }
  footer { margin-top: 16px; color: var(--admin-muted); font-size: 12px; line-height: 1.5; }
</style>
