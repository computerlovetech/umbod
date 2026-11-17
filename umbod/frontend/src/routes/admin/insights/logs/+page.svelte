<script lang="ts">
  import AnalyticsWorkspace from '#lib/components/admin/analytics/AnalyticsWorkspace.svelte';
  import { getInsightsState } from '#lib/components/admin/insights/insights-context.js';

  const state = getInsightsState().createAnalytics();
</script>

<svelte:head><title>Log analytics · Insights</title></svelte:head>
<AnalyticsWorkspace {state} />
