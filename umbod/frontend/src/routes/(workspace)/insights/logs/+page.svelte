<script lang="ts">
  import AnalyticsWorkspace from '#lib/components/shared/analytics/AnalyticsWorkspace.svelte';
  import { createPersonalAnalyticsState } from '#lib/insights/analytics/personal-analytics-state.js';

  const state = createPersonalAnalyticsState();
</script>

<svelte:head><title>Log analytics · Insights</title></svelte:head>
<AnalyticsWorkspace {state} />
