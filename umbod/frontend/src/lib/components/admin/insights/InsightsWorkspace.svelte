<script lang="ts">
  import { onMount, onDestroy, untrack, type Snippet } from 'svelte';
  import '$lib/styles/insights.css';
  import SubpageContainer from '$lib/components/shared/workspace/SubpageContainer.svelte';
  import SubpageNavigation from '$lib/components/shared/workspace/SubpageNavigation.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import ButtonLink from '$lib/components/admin/shared/ButtonLink.svelte';
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

{#snippet actions()}
  {#if route.configuration}
    {#if state.behaviour.configuration.loaded}<Button disabled={state.behaviour.configuration.busy} onclick={state.behaviour.configuration.addPattern}>Add pattern</Button>{/if}
  {:else if route.activeId === 'behaviour'}
    <ButtonLink href="/admin/insights/agent-behaviour/configuration">Configure</ButtonLink>
  {/if}
{/snippet}

<SubpageContainer title="Insights" lede="" actions={state.allowed ? actions : undefined}>
  {#snippet navigation()}
    {#if state.allowed}<SubpageNavigation links={insightsLinks} activeId={route.activeId} label="Insights views" current={route.configuration ? 'location' : 'page'} />{/if}
  {/snippet}
  {#if state.allowed}
    {@render children()}
  {:else}
    <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
  {/if}
</SubpageContainer>
