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
    border: 1px solid #e9e9e7;
    border-radius: 10px;
    color: #37352f;
    display: grid;
    grid-template-columns: 248px minmax(0, 1fr);
    min-height: 540px;
    overflow: hidden;
  }

  .admin-split-workspace__sidebar {
    background: #fafaf9;
    border-right: 1px solid #e9e9e7;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .admin-split-workspace__sidebar-heading {
    color: #afaeab;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 13px 15px 9px;
    text-transform: uppercase;
  }

  .admin-split-workspace__sidebar-heading strong {
    background: #ffffff;
    border: 1px solid #e9e9e7;
    border-radius: 999px;
    color: #787774;
    float: right;
    font-size: 11px;
    letter-spacing: 0;
    padding: 1px 7px;
  }

  .admin-split-workspace__detail {
    min-width: 0;
    padding: 24px 28px;
  }

  @media (max-width: 820px) {
    .admin-split-workspace {
      grid-template-columns: 1fr;
    }

    .admin-split-workspace__sidebar {
      border-bottom: 1px solid #e9e9e7;
      border-right: 0;
    }
  }
</style>
