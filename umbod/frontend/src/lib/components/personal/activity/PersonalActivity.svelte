<script lang="ts">
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DelayedSpinner from '#lib/components/admin/shared/DelayedSpinner.svelte';
  import SegmentedRadio from '#lib/components/shared/SegmentedRadio.svelte';
  import DashboardContainer from '#lib/components/shared/dashboard/DashboardContainer.svelte';
  import DashboardPeriodSwitch from '#lib/components/shared/dashboard/DashboardPeriodSwitch.svelte';
  import McpUsageCharts from './McpUsageCharts.svelte';
  import type { ActivityState } from '#lib/insights/activity/activity-state.svelte.js';
  import HarnessMetrics from './HarnessMetrics.svelte';
  import HarnessSessionPicker from './HarnessSessionPicker.svelte';
  import HarnessSessionReport from './HarnessSessionReport.svelte';

  let { state }: { state: ActivityState } = $props();
  const sources = [
    { value: 'mcp', label: 'MCP Activity' },
    { value: 'harness', label: 'Harness activity' }
  ];

  function search(event: SubmitEvent): void {
    event.preventDefault();
    if (!(event.currentTarget instanceof HTMLFormElement)) return;
    const query = new FormData(event.currentTarget).get('q');
    if (typeof query === 'string') state.searchSessions(query.trim());
  }
</script>

<DashboardContainer title="Activity" showTitle={false}>
  {#snippet actions()}
    <div class="activity-toolbar">
      <SegmentedRadio label="Activity source" options={sources} value={state.source} onchange={state.selectSource} size="compact" />
      <div class="view-controls">
        {#if state.selected}
          <Button variant="secondary" onclick={state.backToOverview}>Back to overview</Button>
        {:else}
          <DashboardPeriodSwitch value={state.days} onchange={state.selectPeriod} />
        {/if}
        <Button variant="secondary" onclick={state.refresh}>{state.selected ? 'Refresh session' : 'Refresh activity'}</Button>
      </div>
    </div>
  {/snippet}
  {@const overview = state.overviewSummary}
  {@const sessionPage = state.sessionPage}
  {#if state.source === 'harness'}
    <details class="session-search">
      <summary>Search session</summary>
      <div class="search-content">
        <form onsubmit={search} role="search" aria-label="Harness sessions">
          <input type="search" name="q" aria-label="Search sessions" value={state.search} maxlength="128" placeholder="Session ID, client, or UTC date" />
          <Button type="submit" variant="secondary">Search</Button>
        </form>
        <div aria-busy={state.sessions.kind === 'loading' || state.pagination === 'loading'}>
          <DelayedSpinner active={state.sessions.kind === 'loading'} label="Loading harness sessions" />
          {#if sessionPage && sessionPage.sessions.length > 0}
            <HarnessSessionPicker sessions={sessionPage.sessions} selected={state.selected} onselect={state.openSession} />
            {#if sessionPage.page.kind === 'more'}
              {#if state.pagination !== 'loading' && state.pagination !== 'idle'}
                <p class="admin-message" role="alert">Could not load more sessions.</p>
              {/if}
              <Button variant="secondary" onclick={state.loadMore} disabled={state.pagination === 'loading'}>
                {state.pagination === 'loading' ? 'Loading more…' : 'Load more sessions'}
              </Button>
            {/if}
          {:else if sessionPage}
            <p class="admin-message" role="status">{state.search ? 'No matching sessions.' : 'No harness sessions in this period.'}</p>
          {:else if state.sessions.kind === 'unavailable' || state.sessions.kind === 'error' || state.sessions.kind === 'missing'}
            <p class="admin-message" role="status">{state.sessions.kind === 'unavailable' ? 'Harness sessions are unavailable.' : 'Could not load harness sessions.'}</p>
            <Button variant="secondary" onclick={state.loadSessions}>Retry sessions</Button>
          {/if}
        </div>
      </div>
    </details>
  {/if}

  {#if state.selected}
    <section class="session-detail" aria-label="Session statistics" aria-busy={state.report.kind === 'loading'}>
      <DelayedSpinner active={state.report.kind === 'loading'} label="Loading session detail" />
      {#if state.report.kind === 'ready'}
        <HarnessSessionReport report={state.report.value} />
      {:else if state.report.kind === 'missing'}
        <p class="admin-message" role="status">This session is no longer available.</p>
      {:else if state.report.kind === 'unavailable' || state.report.kind === 'error'}
        <p class="admin-message" role="alert">{state.report.kind === 'unavailable' ? 'Session detail is unavailable.' : 'Could not load session detail.'}</p>
        <Button variant="secondary" onclick={state.retrySession}>Retry session detail</Button>
      {/if}
    </section>
  {:else}
    <div aria-busy={state.overview.kind === 'loading'}>
      <DelayedSpinner active={state.overview.kind === 'loading'} label="Loading activity summary" />
      {#if state.overview.kind === 'error'}
        <p class="admin-message" role="alert">Could not load the activity summary.</p>
      {:else if state.source === 'harness'}
        {#if overview?.harness.status === 'available'}
          {@const summary = overview.harness.summary}
          <div class="metrics">
            <HarnessMetrics outcomes={summary.outcomes} tools={summary.top_tools} skills={summary.skill_activations} />
          </div>
        {:else if overview?.harness.status === 'unavailable'}
          <p class="admin-message" role="status">Harness activity is unavailable.</p>
        {/if}
      {:else if overview?.mcp.status === 'available'}
        <div class="metrics"><McpUsageCharts charts={state.mcpCharts} /></div>
      {:else if overview?.mcp.status === 'unavailable'}
        <p class="admin-message" role="status">MCP activity is unavailable.</p>
      {/if}
    </div>
  {/if}
</DashboardContainer>

<style>
  .activity-toolbar { display: flex; width: 100%; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 12px; }
  .view-controls { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
  .metrics { display: grid; gap: 20px; }
  .session-search { min-width: 0; border: 1px solid var(--admin-border); border-radius: var(--admin-radius-panel); background: var(--admin-panel); }
  summary { box-sizing: border-box; min-height: 44px; padding: 0.875rem 1.25rem; cursor: pointer; font-size: 0.875rem; font-weight: 600; }
  summary:focus-visible, input:focus-visible { outline: 2px solid var(--admin-focus); outline-offset: 2px; }
  .search-content { padding: 0 1.25rem 1.25rem; }
  form { display: flex; flex-wrap: wrap; align-items: center; gap: 0.625rem; margin-bottom: 0.75rem; }
  input { box-sizing: border-box; width: min(100%, 22rem); padding: 0.5rem 0.75rem; border: 1px solid var(--admin-border); border-radius: var(--admin-radius); background: var(--admin-panel); color: var(--admin-ink); font: inherit; }
  .session-detail { display: flex; flex-direction: column; align-items: stretch; gap: 20px; min-width: 0; }
</style>
