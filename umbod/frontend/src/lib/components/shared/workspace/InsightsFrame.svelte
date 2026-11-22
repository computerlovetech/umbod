<script lang="ts">
  import type { Snippet } from 'svelte';
  import '#lib/styles/insights.css';
  import SubpageContainer from './SubpageContainer.svelte';
  import SubpageNavigation, { type SubpageLink } from './SubpageNavigation.svelte';

  let { links, activeId, children }: { links: readonly SubpageLink[]; activeId: string; children: Snippet } = $props();
</script>

<SubpageContainer title="Insights">
  {#snippet navigation()}
    <SubpageNavigation {links} {activeId} label="Insights views" />
  {/snippet}
  {@render children()}
</SubpageContainer>
