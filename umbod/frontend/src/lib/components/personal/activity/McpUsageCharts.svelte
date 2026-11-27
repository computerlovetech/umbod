<script lang="ts">
  import DashboardRow from '#lib/components/shared/dashboard/DashboardRow.svelte';
  import DashboardColumn from '#lib/components/shared/dashboard/DashboardColumn.svelte';
  import DashboardPanel from '#lib/components/shared/dashboard/DashboardPanel.svelte';
  import OutcomeRing from '#lib/components/shared/dashboard/visualizations/OutcomeRing.svelte';
  import OperationMixChart from '#lib/components/shared/dashboard/visualizations/OperationMixChart.svelte';
  import DailyActivityChart from '#lib/components/shared/dashboard/visualizations/DailyActivityChart.svelte';
  import ToolRankingList from '#lib/components/shared/dashboard/visualizations/ToolRankingList.svelte';
  import type { ActivityChart, OperationChart, OutcomeChart, RankedTool } from '#lib/components/shared/dashboard/visualizations/types.js';

  let { charts }: {
    charts: {
      readonly outcomes: OutcomeChart;
      readonly mix: OperationChart;
      readonly activity: ActivityChart;
      readonly tools: readonly RankedTool[];
    };
  } = $props();
</script>

<DashboardRow>
  <DashboardColumn span={6}>
    <DashboardPanel title="Tool call outcomes" metadata="All tool outcomes">
      <OutcomeRing data={charts.outcomes} />
    </DashboardPanel>
  </DashboardColumn>
  <DashboardColumn span={6}>
    <DashboardPanel title="Operation mix" metadata="Share of all operations">
      <OperationMixChart data={charts.mix} />
    </DashboardPanel>
  </DashboardColumn>
</DashboardRow>
<DashboardRow>
  <DashboardColumn span={7}>
    <DashboardPanel title="Tool activity" metadata={charts.activity.total > 0 ? `${charts.activity.total.toLocaleString('en')} calls` : undefined}>
      <DailyActivityChart data={charts.activity} />
    </DashboardPanel>
  </DashboardColumn>
  <DashboardColumn span={5}>
    <DashboardPanel title="Most-used tools">
      <ToolRankingList tools={charts.tools} />
    </DashboardPanel>
  </DashboardColumn>
</DashboardRow>
