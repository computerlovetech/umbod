<script lang="ts">
  import AgentBehaviourView from '$lib/components/admin/agent-behaviour/AgentBehaviourView.svelte';
  import { getInsightsState } from '$lib/components/admin/insights/insights-context';

  const state = getInsightsState();
</script>

<svelte:head><title>Agent behaviour · Insights</title></svelte:head>
<AgentBehaviourView state={state.behaviour} />
