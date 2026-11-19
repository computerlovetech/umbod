<script lang="ts">
  import type { Snippet } from 'svelte';
  import Button from './Button.svelte';
  import { attachMobileNavigation } from '#lib/components/shared/workspace/mobile-navigation.js';
  import '#lib/styles/mobile-navigation.css';

  let {
    ariaLabel,
    sidebarLabel,
    sidebarHeading,
    mobileSidebar = false,
    count,
    detailLabel,
    sidebar,
    detail
  }: {
    ariaLabel: string;
    sidebarLabel: string;
    sidebarHeading: string;
    mobileSidebar?: boolean;
    count?: number;
    detailLabel: string;
    sidebar: Snippet;
    detail: Snippet;
  } = $props();

  const sidebarId = $props.id();
</script>

{#snippet sidebarContent()}
  <div class="admin-split-workspace__sidebar-heading">
    <span>{sidebarHeading}</span>
    {#if count !== undefined}
      <strong>{count}</strong>
    {/if}
  </div>
  {@render sidebar()}
{/snippet}

<section class="admin-split-workspace" aria-label={ariaLabel}>
  {#if mobileSidebar}
    <div class="mobile-navigation-trigger split-navigation-trigger">
      <Button variant="quiet" popovertarget={sidebarId}>
        <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"><path d="M3 6h6l2 3h10v10H3z" /></svg>
        {sidebarHeading}
      </Button>
    </div>
    <aside class="admin-split-workspace__sidebar mobile-navigation-panel" id={sidebarId} aria-label={sidebarLabel} {@attach attachMobileNavigation}>
      <div class="mobile-navigation-close">
        <Button variant="quiet" iconOnly aria-label={`Close ${sidebarLabel.toLowerCase()}`} popovertarget={sidebarId} popovertargetaction="hide">
          <svg aria-hidden="true" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
        </Button>
      </div>
      {@render sidebarContent()}
    </aside>
  {:else}
    <aside class="admin-split-workspace__sidebar" aria-label={sidebarLabel}>
      {@render sidebarContent()}
    </aside>
  {/if}

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
    padding: var(--split-workspace-detail-padding, 24px 28px);
  }

  @media (max-width: 720px) {
    .admin-split-workspace:has(.split-navigation-trigger) {
      grid-template-columns: minmax(0, 1fr);
      grid-template-rows: auto 1fr;
    }

    .split-navigation-trigger {
      background: var(--admin-soft);
      border-bottom: 1px solid var(--admin-border);
      padding-inline: 0.5rem;
    }
  }

  @media (max-width: 480px) {
    .admin-split-workspace__detail {
      padding: var(--split-workspace-detail-padding, 20px 16px);
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
