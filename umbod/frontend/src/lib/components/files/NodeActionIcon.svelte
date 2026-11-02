<script lang="ts">
  let { action }: { action: 'share' | 'rename' | 'description' | 'move' | 'delete' | 'retry' | 'sign-in' } = $props();
</script>

<svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  {#if action === 'share'}
    <circle cx="18" cy="5" r="3" /><circle cx="6" cy="12" r="3" /><circle cx="18" cy="19" r="3" /><path d="m8.6 10.5 6.8-4M8.6 13.5l6.8 4" />
  {:else if action === 'rename'}
    <path d="m15 4 5 5M4 20l5-1L21 7a2.1 2.1 0 0 0-5-5L4 14zM4 20h16" />
  {:else if action === 'description'}
    <path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6" />
  {:else if action === 'move'}
    <path d="M3 7V5h7l2 3h9v12H3v-3M2 12h12m-4-4 4 4-4 4" />
  {:else if action === 'delete'}
    <path d="M3 6h18M9 6V4h6v2M5 6l1 14h12l1-14M10 10v6M14 10v6" />
  {:else if action === 'retry'}
    <path d="M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M5 15a8 8 0 0 0 13 3" />
  {:else}
    <path d="M14 3h6v18h-6M3 12h12m-4-4 4 4-4 4" />
  {/if}
</svg>

<style>
  svg { flex-shrink: 0; }
</style>
