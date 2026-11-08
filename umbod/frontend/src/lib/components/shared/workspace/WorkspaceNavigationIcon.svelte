<script lang="ts">
  import type { WorkspaceNavigationIcon } from '$lib/workspace/navigation';

  let { name }: { name: WorkspaceNavigationIcon } = $props();
</script>

<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
  {#if name === 'dashboard'}
    <rect x="3" y="3" width="7" height="7" rx="1" />
    <rect x="14" y="3" width="7" height="7" rx="1" />
    <rect x="3" y="14" width="7" height="7" rx="1" />
    <rect x="14" y="14" width="7" height="7" rx="1" />
  {:else if name === 'files'}
    <path d="M3 7V4h7l2 3h9v13H3Z" />
  {:else if name === 'gettingStarted'}
    <path d="m13 2-9 12h7l-1 8 10-13h-8Z" />
  {:else if name === 'administration'}
    <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z" />
    <path d="m8 12 3 3 5-6" />
  {:else if name === 'connectors'}
    <path d="M9 3v4m6-4v4M12 16v5" />
    <path d="M6 7h12v3a6 6 0 0 1-12 0Z" />
  {:else if name === 'groups'}
    <circle cx="9" cy="8" r="3" />
    <path d="M3 21v-2a6 6 0 0 1 12 0v2M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 5v2" />
  {:else if name === 'permissions'}
    <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6Z" />
    <circle cx="12" cy="10" r="2" />
    <path d="M12 12v4" />
  {:else if name === 'analytics'}
    <path d="M3 3v18h18M8 16v-5m5 5V6m5 10V9" />
  {:else if name === 'settings'}
    <path d="m9 3-.5 2-2 1-2-.5-2 3.5L4 10.5v3L2.5 15l2 3.5 2-.5 2 1 .5 2h4l.5-2 2-1 2 .5 2-3.5-1.5-1.5v-3L20 9l-2-3.5-2 .5-2-1-.5-2Z" />
    <circle cx="11.5" cy="12" r="3" />
  {/if}
</svg>

<style>
  svg {
    fill: none;
    flex-shrink: 0;
    height: 17px;
    stroke: currentColor;
    stroke-width: 1.6;
    width: 17px;
  }
</style>
