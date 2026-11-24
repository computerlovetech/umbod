<script lang="ts">
  import { onDestroy } from 'svelte';
  import { page } from '$app/state';
  import { createPersonalReportsState } from '#lib/agent-behaviour/state/personal-reports-state.svelte.js';
  import PersonalAgentBehaviourView from '#lib/components/personal/agent-behaviour/PersonalAgentBehaviourView.svelte';

  const state = createPersonalReportsState();
  onDestroy(state.dispose);
</script>

<svelte:head><title>Agent behaviour · Insights</title></svelte:head>
<PersonalAgentBehaviourView {state} reportId={page.url.searchParams.get('report')} />
