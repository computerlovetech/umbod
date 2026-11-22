<script lang="ts">
  import { onMount, onDestroy, untrack, type Snippet } from 'svelte';
  import '#lib/styles/insights.css';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import SubpageNavigation from '#lib/components/shared/workspace/SubpageNavigation.svelte';
  import { setInsightsState } from './insights-context';
  import { createInsightsState } from './insights-factory';
  import { InsightsNavigation, insightsLinks } from './insights-navigation';
  import type { InsightsState } from './insights-state.svelte';

  let { pathname, children, createState = createInsightsState }: {
    pathname: string;
    children: Snippet;
    createState?: () => InsightsState;
  } = $props();
  const state = untrack(() => createState());
  const route = new InsightsNavigation(() => pathname);
  setInsightsState(state);
  onMount(state.start);
  onDestroy(state.dispose);
</script>

{#if !state.allowed}
  <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
{:else if route.diagnostics}
  {@render children()}
{:else}
  <SubpageContainer title="Insights">
    {#snippet navigation()}
      <SubpageNavigation links={insightsLinks} activeId={route.activeId} label="Insights views" />
    {/snippet}
    {@render children()}
  </SubpageContainer>
{/if}
