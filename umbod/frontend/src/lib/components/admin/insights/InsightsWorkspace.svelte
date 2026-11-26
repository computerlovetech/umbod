<script lang="ts">
  import { beforeNavigate } from '$app/navigation';
  import { onMount, onDestroy, untrack, type Snippet } from 'svelte';
  import '#lib/styles/insights.css';
  import InsightsFrame from '#lib/components/shared/workspace/InsightsFrame.svelte';
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

  beforeNavigate(({ to, type, willUnload, shallow, cancel }): void => {
    if (shallow) return;
    const routeId = to?.route.id;
    const legacyReporting = to?.url.searchParams.get('tab') === 'reporting'
      && (routeId === '/admin/(agent-insights)/agent-diagnostics' || routeId === '/admin/(agent-insights)/insights/agent-behaviour/configuration');
    if (!willUnload && !legacyReporting && routeId?.startsWith('/admin/(agent-insights)/')) return;
    const configuration = state.behaviour.configuration;
    if (!configuration.dirty && !configuration.editorDirty) return;
    if (type === 'leave' || !window.confirm('Leave and lose your unsaved Agent diagnostics changes?')) cancel();
  });

  onMount(state.start);
  onDestroy(state.dispose);
</script>

{#if !state.allowed}
  <p class="admin-message admin-message--error" role="alert">Administration access is no longer available. Reload or sign in again.</p>
{:else if route.diagnostics}
  {@render children()}
{:else}
  <InsightsFrame links={insightsLinks} activeId={route.activeId}>
    {@render children()}
  </InsightsFrame>
{/if}
