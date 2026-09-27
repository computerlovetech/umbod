<script lang="ts">
  import type { Snippet } from 'svelte';

  let {
    ariaLabel,
    sidebarLabel,
    sidebarHeading,
    count,
    detailLabel,
    sidebar,
    detail
  }: {
    ariaLabel: string;
    sidebarLabel: string;
    sidebarHeading: string;
    count?: number;
    detailLabel: string;
    sidebar: Snippet;
    detail: Snippet;
  } = $props();
</script>

<section class="admin-split-workspace" aria-label={ariaLabel}>
  <aside class="admin-split-workspace__sidebar" aria-label={sidebarLabel}>
    <div class="admin-split-workspace__sidebar-heading">
      <span>{sidebarHeading}</span>
      {#if count !== undefined}
        <strong>{count}</strong>
      {/if}
    </div>
    {@render sidebar()}
  </aside>

  <section class="admin-split-workspace__detail" aria-label={detailLabel}>
    {@render detail()}
  </section>
</section>

<style>
  .admin-split-workspace {
    border: 1px solid var(--admin-border);
    background: var(--admin-panel);
    border-radius: var(--admin-radius-panel);
    color: var(--admin-ink);
    display: grid;
    grid-template-columns: 248px minmax(0, 1fr);
    min-height: 540px;
    overflow: hidden;
  }

  .admin-split-workspace__sidebar {
    background: var(--admin-soft);
    border-right: 1px solid var(--admin-border);
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .admin-split-workspace__sidebar-heading {
    color: var(--admin-muted);
    font-family: var(--admin-mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.5px;
    padding: 18px 16px;
    text-transform: uppercase;
  }

  .admin-split-workspace__sidebar-heading strong {
    background: var(--admin-panel);
    border: 1px solid var(--admin-border);
    border-radius: 999px;
    color: var(--admin-muted);
    float: right;
    font-size: 11px;
    letter-spacing: 0;
    padding: 1px 7px;
  }

  .admin-split-workspace__detail {
    min-width: 0;
    padding: 24px 28px;
  }

  @media (max-width: 480px) {
    .admin-split-workspace__detail {
      padding: 20px 16px;
    }
  }

  @container (max-width: 760px) {
    .admin-split-workspace {
      grid-template-columns: 1fr;
    }

    .admin-split-workspace__sidebar {
      border-bottom: 1px solid var(--admin-border);
      border-right: 0;
    }
  }
</style>
