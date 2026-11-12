<script lang="ts">
  import type { Snippet } from 'svelte';

  let { span, children }: { span: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12; children: Snippet } = $props();
</script>

<div class="dashboard-column" style:--dashboard-span={span}>{@render children()}</div>

<style>
  .dashboard-column { grid-column: span var(--dashboard-span); display: flex; flex-direction: column; min-width: 0; }
  @container dashboard-layout (max-width: 760px) { .dashboard-column { grid-column: 1 / -1; } }
</style>
