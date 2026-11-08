<script module lang="ts">
  export interface SubpageLink {
    readonly id: string;
    readonly label: string;
    readonly href: string;
  }
</script>

<script lang="ts">
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';

  let { links, activeId, label, pending = false, loadingLabel = 'Loading page' }: {
    links: readonly SubpageLink[];
    activeId: string;
    label: string;
    pending?: boolean;
    loadingLabel?: string;
  } = $props();
</script>

<nav aria-label={label}>
  {#each links as link (link.id)}
    <a class={['subpage-link', { active: activeId === link.id }]} href={link.href} aria-current={activeId === link.id ? 'page' : undefined}>{link.label}</a>
  {/each}
</nav>
{#if pending}
  <div class="navigation-loading"><DelayedSpinner active label={loadingLabel} /></div>
{/if}

<style>
  nav { border-bottom: 1px solid var(--admin-border); display: flex; flex-wrap: wrap; gap: 12px 24px; margin-bottom: 32px; }
  a { border-bottom: 2px solid transparent; color: var(--admin-muted); font-size: 14px; font-weight: 600; margin-bottom: -1px; padding: 0 2px 10px; text-decoration: none; }
  a:hover { color: var(--admin-ink); }
  a.active { border-bottom-color: var(--admin-accent); color: var(--admin-accent); }
  .navigation-loading { display: flex; justify-content: center; margin: -16px 0 16px; min-height: 18px; }
</style>
