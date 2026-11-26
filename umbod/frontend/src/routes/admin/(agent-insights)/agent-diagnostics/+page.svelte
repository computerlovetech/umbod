<script lang="ts">
  import ConfigurationView from '#lib/components/admin/agent-behaviour/ConfigurationView.svelte';
  import { getInsightsState } from '#lib/components/admin/insights/insights-context.js';

  const state = getInsightsState();
</script>

<svelte:head><title>Agent diagnostics</title></svelte:head>
<ConfigurationView state={state.behaviour.configuration} />
