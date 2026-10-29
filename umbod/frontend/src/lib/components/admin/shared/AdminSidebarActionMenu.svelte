<script lang="ts">
  import type { Snippet } from 'svelte';
  import ActionMenu from '$lib/components/shared/ActionMenu.svelte';

  let { open, label, menu, onopenchange }: { open: boolean; label: string; menu: Snippet; onopenchange: (open: boolean) => void } = $props();
</script>

<ActionMenu {open} {label} {menu} {onopenchange}>
  {#snippet trigger()}⋯{/snippet}
</ActionMenu>
