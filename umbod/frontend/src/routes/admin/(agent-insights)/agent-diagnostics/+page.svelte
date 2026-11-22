<script lang="ts">
  import { page } from '$app/state';
  import ConfigurationView from '#lib/components/admin/agent-behaviour/ConfigurationView.svelte';
  import { getInsightsState } from '#lib/components/admin/insights/insights-context.js';

  const state = getInsightsState();
</script>

<svelte:head><title>Agent diagnostics</title></svelte:head>
<ConfigurationView state={state.behaviour.configuration} section={page.url.searchParams.get('tab') === 'reporting' ? 'reporting' : 'patterns'} />
