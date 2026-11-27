<script lang="ts">
  import DashboardPanel from '#lib/components/shared/dashboard/DashboardPanel.svelte';
  import ToolRankingList from '#lib/components/shared/dashboard/visualizations/ToolRankingList.svelte';
  import { harnessRanking } from '#lib/insights/activity/presentation.js';
  import type { ActivitySessionReport } from '#lib/insights/activity/domain/activity-schemas.js';
  import HarnessMetrics from './HarnessMetrics.svelte';

  let { report }: { report: ActivitySessionReport } = $props();
</script>

<HarnessMetrics outcomes={report.session.outcomes} tools={report.top_tools} skills={report.skill_activations} />
<DashboardPanel title="Failed tools">
  {#if report.failed_tools.length > 0}
    <ToolRankingList tools={harnessRanking(report.failed_tools)} label="Tools by failed call count" />
    {#if report.has_more_failed_tools}<p class="admin-message">Showing the top 100 failed tools.</p>{/if}
  {:else}
    <p class="admin-message">No named failed tools.</p>
  {/if}
</DashboardPanel>
