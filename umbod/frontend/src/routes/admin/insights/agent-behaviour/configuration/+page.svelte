<script lang="ts">
  import ConfigurationView from '#lib/components/admin/agent-behaviour/ConfigurationView.svelte';
  import { getInsightsState } from '#lib/components/admin/insights/insights-context.js';

  const state = getInsightsState();
</script>

<svelte:head><title>Configuration · Agent behaviour · Insights</title></svelte:head>
<ConfigurationView state={state.behaviour.configuration} />
