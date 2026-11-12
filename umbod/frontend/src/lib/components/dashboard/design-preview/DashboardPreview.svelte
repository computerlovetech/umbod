<script lang="ts">
  import WorkspaceShell from '$lib/components/shared/workspace/WorkspaceShell.svelte';
  import Button from '$lib/components/admin/shared/Button.svelte';
  import { workspaceNavigation, workspacePresentation } from '$lib/workspace/navigation';
  import { DashboardPreviewState } from './preview-state.svelte';
  import DashboardContainer from '$lib/components/shared/dashboard/DashboardContainer.svelte';
  import DashboardPeriodSwitch from '$lib/components/shared/dashboard/DashboardPeriodSwitch.svelte';
  import DashboardRow from '$lib/components/shared/dashboard/DashboardRow.svelte';
  import DashboardColumn from '$lib/components/shared/dashboard/DashboardColumn.svelte';
  import DashboardPanel from '$lib/components/shared/dashboard/DashboardPanel.svelte';
  import OutcomeRing from '$lib/components/shared/dashboard/visualizations/OutcomeRing.svelte';
  import OperationMixChart from '$lib/components/shared/dashboard/visualizations/OperationMixChart.svelte';
  import DailyActivityChart from '$lib/components/shared/dashboard/visualizations/DailyActivityChart.svelte';
  import ToolRankingList from '$lib/components/shared/dashboard/visualizations/ToolRankingList.svelte';

  const state = new DashboardPreviewState();
</script>

<svelte:head><title>Dashboard design preview · Umbod</title></svelte:head>

<WorkspaceShell {...workspacePresentation} navigationItems={workspaceNavigation(false)} activeItem="dashboard" accountFallback="Design preview" contentWidth="wide">
  <div class="preview-heading"><h1 class="admin-title">Dashboard</h1></div>
  <DashboardContainer title="Your usage">
    {#snippet actions()}
      <span class="preview-label">Preview · {state.scenario === 'empty' ? 'empty state' : 'sample data'}</span>
      <div class="scenario-switch" role="group" aria-label="Preview data">
        <Button variant={state.scenario === 'sample' ? 'secondary' : 'quiet'} aria-pressed={state.scenario === 'sample'} onclick={() => state.setScenario('sample')}>Sample data</Button>
        <Button variant={state.scenario === 'empty' ? 'secondary' : 'quiet'} aria-pressed={state.scenario === 'empty'} onclick={() => state.setScenario('empty')}>Empty state</Button>
      </div>
      <DashboardPeriodSwitch value={state.period} onchange={state.setPeriod} />
      <a class="back-link" href="/dashboard" aria-label="Back to live dashboard">Exit preview ↗</a>
    {/snippet}
    <DashboardRow>
      <DashboardColumn span={6}>
        <DashboardPanel title="Tool call outcomes" metadata="All tool outcomes">
          <OutcomeRing data={state.outcomeChart} />
        </DashboardPanel>
      </DashboardColumn>
      <DashboardColumn span={6}>
        <DashboardPanel title="Operation mix" metadata="Share of all operations">
          <OperationMixChart data={state.operationChart} />
        </DashboardPanel>
      </DashboardColumn>
    </DashboardRow>
    <DashboardRow>
      <DashboardColumn span={7}>
        <DashboardPanel title="Tool activity" metadata={state.totals.all > 0 ? `${state.totals.all.toLocaleString('en')} calls` : undefined}>
          <DailyActivityChart data={state.activityChart} />
        </DashboardPanel>
      </DashboardColumn>
      <DashboardColumn span={5}>
        <DashboardPanel title="Most-used tools" metadata="Top 5 · calls ↓">
          {#snippet actions()}
            {#if state.scenario === 'sample'}
            <fieldset class="connector-filter">
              <legend>Filter ranking by connector</legend>
              <div class="connector-options">
                {#each state.connectors as connector (connector)}
                  <label class={['connector-option', state.selectedConnectors.includes(connector) && 'selected']}>
                    <input type="checkbox" checked={state.selectedConnectors.includes(connector)} onchange={(event) => state.setConnectorSelected(connector, event.currentTarget.checked)} />
                    {connector}
                  </label>
                {/each}
              </div>
            </fieldset>
            {/if}
          {/snippet}
          <div aria-live="polite" aria-atomic="true">
            <ToolRankingList tools={state.topTools} />
            {#if state.scenario === 'sample' && state.topTools.length === 0}<Button variant="secondary" onclick={state.selectAllConnectors}>Select all connectors</Button>{/if}
          </div>
        </DashboardPanel>
      </DashboardColumn>
    </DashboardRow>
    {#snippet footer()}
      <div class="preview-footer"><span>{state.activityChart.days[0].label} – {state.activityChart.days[state.activityChart.days.length - 1].label}, 2026 · UTC</span><span>Design preview · not connected to your account</span></div>
    {/snippet}
  </DashboardContainer>
</WorkspaceShell>

<style>
  .preview-heading { margin-bottom: 28px; }
  .scenario-switch { display: inline-flex; gap: 2px; align-items: center; }
  .preview-label { font-size: 12px; color: var(--admin-accent); background: var(--admin-accent-soft); padding: 5px 8px; border-radius: 4px; }
  .back-link { color: var(--admin-muted); text-decoration: none; font-size: 12px; }
  .back-link:hover { color: var(--admin-accent); text-decoration: underline; }
  .connector-filter { border: 0; border-bottom: 1px solid var(--admin-border); margin: 0; padding: 0 0 12px; min-width: 0; }
  .connector-filter legend { color: var(--admin-muted); font-size: 12px; padding: 0; margin-bottom: 8px; }
  .connector-options { display: flex; flex-wrap: wrap; gap: 6px; }
  .connector-option { display: inline-flex; align-items: center; gap: 6px; padding: 7px 9px; border: 1px solid var(--admin-border); border-radius: 4px; color: var(--admin-muted); font-size: 12px; cursor: pointer; }
  .connector-option.selected { background: var(--admin-accent-soft); border-color: var(--admin-accent-border); color: var(--admin-accent); }
  .connector-option input { accent-color: var(--admin-accent); margin: 0; width: 14px; height: 14px; }
  .preview-footer { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; }
</style>
