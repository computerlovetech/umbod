<script lang="ts">
  import DashboardRow from '#lib/components/shared/dashboard/DashboardRow.svelte';
  import DashboardColumn from '#lib/components/shared/dashboard/DashboardColumn.svelte';
  import DashboardPanel from '#lib/components/shared/dashboard/DashboardPanel.svelte';
  import OutcomeRing from '#lib/components/shared/dashboard/visualizations/OutcomeRing.svelte';
  import ToolRankingList from '#lib/components/shared/dashboard/visualizations/ToolRankingList.svelte';
  import { projectOutcomes } from '#lib/dashboard/chart-projections.js';
  import { harnessRanking } from '#lib/insights/activity/presentation.js';

  let { outcomes, tools, skills }: {
    outcomes: { readonly success: number; readonly failure: number; readonly unknown: number };
    tools: readonly { readonly tool_name: string; readonly count: number }[];
    skills: number;
  } = $props();
</script>

<DashboardRow>
  <DashboardColumn span={5}>
    <DashboardPanel title="Tool call outcomes">
      <OutcomeRing data={projectOutcomes(outcomes)} showEmptyCounts />
    </DashboardPanel>
  </DashboardColumn>
  <DashboardColumn span={5}>
    <DashboardPanel title="Most-used tools">
      {#if tools.length > 0}
        <ToolRankingList tools={harnessRanking(tools)} />
      {:else}
        <p class="admin-message">No named tool calls.</p>
      {/if}
    </DashboardPanel>
  </DashboardColumn>
  <DashboardColumn span={2}>
    <DashboardPanel title="Skill activations">
      <strong>{skills.toLocaleString('en')}</strong>
    </DashboardPanel>
  </DashboardColumn>
</DashboardRow>

<style>
  strong { font-size: 1.5rem; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
</style>
