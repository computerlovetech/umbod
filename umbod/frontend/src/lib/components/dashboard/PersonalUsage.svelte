<script lang="ts">
  import Button from '$lib/components/admin/shared/Button.svelte';
  import DashboardPeriodSwitch from '$lib/components/shared/dashboard/DashboardPeriodSwitch.svelte';
  import DelayedSpinner from '$lib/components/admin/shared/DelayedSpinner.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';
  import type { UsageState } from '$lib/dashboard/state/usage-state.svelte';
  import DashboardContainer from '$lib/components/shared/dashboard/DashboardContainer.svelte';
  import DashboardRow from '$lib/components/shared/dashboard/DashboardRow.svelte';
  import DashboardColumn from '$lib/components/shared/dashboard/DashboardColumn.svelte';
  import DashboardPanel from '$lib/components/shared/dashboard/DashboardPanel.svelte';
  import OutcomeRing from '$lib/components/shared/dashboard/visualizations/OutcomeRing.svelte';
  import OperationMixChart from '$lib/components/shared/dashboard/visualizations/OperationMixChart.svelte';
  import DailyActivityChart from '$lib/components/shared/dashboard/visualizations/DailyActivityChart.svelte';
  import ToolRankingList from '$lib/components/shared/dashboard/visualizations/ToolRankingList.svelte';

  let { state, signIn }: { state: UsageState; signIn: () => void } = $props();
</script>

<div class="usage" aria-busy={state.pending}>
  <DashboardContainer title="Your usage">
    {#snippet actions()}
      <DashboardPeriodSwitch value={state.days} onchange={(period) => state.selectPeriod(String(period))} />
      <Button variant="secondary" disabled={state.pending} onclick={state.refresh}>Refresh usage</Button>
    {/snippet}
    <DelayedSpinner active={state.pending} label="Loading usage" />
    {#if state.phase === 'sign-in'}
      <div class="admin-message" role="alert">Sign in required</div>
      <Button onclick={signIn}>Sign in</Button>
    {:else if state.phase === 'forbidden'}
      <div class="admin-message" role="alert">Usage access unavailable</div>
      <Button variant="secondary" onclick={state.refresh}>Retry usage</Button>
    {:else if state.phase === 'error' || state.phase === 'unavailable'}
      <div class="admin-message" role="alert">{state.phase === 'unavailable' ? 'Usage unavailable' : "Couldn't load usage"}</div>
      <Button variant="secondary" onclick={state.refresh}>Retry usage</Button>
    {:else if state.snapshot}
      <DashboardRow>
        <DashboardColumn span={6}>
          <DashboardPanel title="Tool call outcomes" metadata="All tool outcomes">
            <OutcomeRing data={state.charts.outcomes} />
          </DashboardPanel>
        </DashboardColumn>
        <DashboardColumn span={6}>
          <DashboardPanel title="Operation mix" metadata="Share of all operations">
            <OperationMixChart data={state.charts.mix} />
          </DashboardPanel>
        </DashboardColumn>
      </DashboardRow>
      <DashboardRow>
        <DashboardColumn span={7}>
          <DashboardPanel title="Tool activity" metadata={state.charts.activity.total > 0 ? `${state.charts.activity.total.toLocaleString('en')} calls` : undefined}>
            <DailyActivityChart data={state.charts.activity} />
          </DashboardPanel>
        </DashboardColumn>
        <DashboardColumn span={5}>
          <DashboardPanel title="Most-used tools">
            <ToolRankingList tools={[]} />
          </DashboardPanel>
        </DashboardColumn>
      </DashboardRow>
    {/if}
    {#snippet footer()}
      {#if state.snapshot}<div class="updated">Updated <DateTimeView value={state.snapshot.as_of} /></div>{/if}
    {/snippet}
  </DashboardContainer>
</div>

<style>
  .usage { margin-top: 1.75rem; }
</style>
