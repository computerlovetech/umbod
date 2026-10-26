<script lang="ts">
  import type { AccessStatus } from '$lib/personal-connections/presentation';

  let { status, compact = false }: { status: AccessStatus; compact?: boolean } = $props();
</script>

<span class={['access-status', status.tone, compact && 'compact']}>
  <svg aria-hidden="true" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6">
    {#if status.tone === 'success'}
      <circle cx="10" cy="10" r="7.25" /><path d="m6.5 10 2.25 2.25 4.75-4.75" />
    {:else if status.tone === 'warning'}
      <path d="m10 2 8.5 15H1.5L10 2Z" stroke-linejoin="round" /><path d="M10 7v4m0 2v.5" />
    {:else if status.tone === 'pending'}
      <circle cx="10" cy="10" r="7.25" /><path d="M10 5.5V10l3 2" />
    {:else}
      <circle cx="10" cy="10" r="7.25" /><path d="M7.5 6.5v7m5-7v7" />
    {/if}
  </svg>
  {status.label}
</span>

<style>
  .access-status { align-items: center; border: 1px solid; border-radius: 999px; display: inline-flex; font-size: 0.75rem; font-weight: 600; gap: 0.35rem; line-height: 1.4; padding: 0.3rem 0.6rem; width: fit-content; }
  .success { background: var(--admin-success-bg); border-color: var(--admin-success-border); color: var(--admin-success-text); }
  .warning { background: var(--admin-warning-bg); border-color: var(--admin-warning-border); color: var(--admin-warning-text); }
  .neutral, .pending { background: var(--admin-soft); border-color: var(--admin-border); color: var(--admin-muted); }
  svg { flex: 0 0 auto; height: 1rem; width: 1rem; }
  .compact { background: transparent; border: 0; border-radius: 0; font-size: 0.7rem; padding: 0; }
  .compact svg { height: 0.85rem; width: 0.85rem; }
</style>
