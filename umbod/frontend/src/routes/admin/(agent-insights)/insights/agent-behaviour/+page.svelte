<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { agentBehaviourFindingsHref } from '#lib/workspace/navigation.js';
  import AgentBehaviourView from '#lib/components/admin/agent-behaviour/AgentBehaviourView.svelte';
  import { getInsightsState } from '#lib/components/admin/insights/insights-context.js';

  const state = getInsightsState();
</script>

<svelte:head><title>Agent behaviour · Insights</title></svelte:head>
<AgentBehaviourView state={state.behaviour} reportId={page.url.searchParams.get('report')} onDeleted={(): Promise<void> => goto(agentBehaviourFindingsHref, { replaceState: true })} />
