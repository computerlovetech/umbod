<script module lang="ts">
  export interface SubpageLink {
    readonly id: string;
    readonly label: string;
    readonly href: string;
  }
</script>

<script lang="ts">
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import '$lib/styles/subpage-navigation.css';

  let { links, activeId, label, current = 'page', pending = false, loadingLabel = 'Loading page' }: {
    links: readonly SubpageLink[];
    activeId: string;
    label: string;
    current?: 'page' | 'location';
    pending?: boolean;
    loadingLabel?: string;
  } = $props();
</script>

<nav class="subpage-navigation" aria-label={label}>
  {#each links as link (link.id)}
    <a class="subpage-navigation-item" href={link.href} aria-current={activeId === link.id ? current : undefined}>{link.label}</a>
  {/each}
</nav>
{#if pending}
  <div class="navigation-loading"><DelayedSpinner active label={loadingLabel} /></div>
{/if}

<style>
  .navigation-loading { display: flex; justify-content: center; margin: -16px 0 16px; min-height: 18px; }
</style>
