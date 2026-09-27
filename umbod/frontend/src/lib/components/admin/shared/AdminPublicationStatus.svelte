<script lang="ts">
  type Props = {
    status: string;
  };

  let { status }: Props = $props();

  const normalizedStatus = $derived(status.toLowerCase());
  const displayStatus = $derived(normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1));
  const tone = $derived(normalizedStatus === 'published' ? 'published' : normalizedStatus === 'draft' || normalizedStatus === 'unconfigured' ? 'draft' : 'neutral');
</script>

<span class={['publication-status', tone]}>{displayStatus}</span>

<style>
  .publication-status {
    border: 1px solid;
    border-radius: 999px;
    flex: 0 0 auto;
    font-size: 0.75rem;
    font-weight: 650;
    line-height: 1;
    padding: 0.35rem 0.55rem;
  }

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
