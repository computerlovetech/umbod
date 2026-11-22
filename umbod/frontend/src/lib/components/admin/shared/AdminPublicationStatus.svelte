<script lang="ts">
  type Props = {
    status: string;
  };

  let { status }: Props = $props();

  const normalizedStatus = $derived(status.toLowerCase());
  const displayStatus = $derived(normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1));
  const tone = $derived(normalizedStatus === 'published' ? 'published' : normalizedStatus === 'draft' || normalizedStatus === 'unconfigured' ? 'draft' : 'neutral');
</script>

<span class={['publication-status', tone]}>
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
    {#if normalizedStatus === 'published'}
      <path d="M3 12s3-6 9-6 9 6 9 6-3 6-9 6-9-6-9-6Z" />
      <circle cx="12" cy="12" r="2" />
    {:else}
      <path d="M4 4l16 16M9 6.5c1-.35 2-.5 3-.5 6 0 9 6 9 6a15 15 0 0 1-2 2.7m-3.3 2.65c-1.1.4-2.35.65-3.7.65-6 0-9-6-9-6a15 15 0 0 1 3-3.6" />
    {/if}
  </svg>
  {displayStatus}
</span>

<style>
  .publication-status {
    align-items: center;
    border: 1px solid;
    border-radius: 999px;
    display: inline-flex;
    flex: 0 0 auto;
    gap: 0.3rem;
    font-size: 0.75rem;
    font-weight: 650;
    line-height: 1;
    padding: 0.35rem 0.55rem;
  }

  svg { flex: none; height: 0.85rem; width: 0.85rem; }

  .published {
    background: var(--admin-success-bg);
    border-color: var(--admin-success-border);
    color: var(--admin-success-text);
  }

  .draft {
    background: var(--admin-warning-bg);
    border-color: var(--admin-warning-border);
    color: var(--admin-warning-text);
  }

  .neutral {
    background: var(--admin-soft);
    border-color: var(--admin-border);
    color: var(--admin-muted);
  }
</style>
