<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '#lib/components/admin/shared/select-state.svelte.js';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import QueryPanel from '#lib/components/shared/workspace/QueryPanel.svelte';
  import { reportStatuses, type ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';
  let { state, listHref }: { state: ReportsState; listHref: string } = $props();
  onMount((): void => state.start());
  onDestroy((): void => state.stopList());
</script>

<QueryPanel id="agent-behaviour-query" summary={state.querySummary} pending={state.busy} onrun={state.runQuery} onreset={state.resetQuery}>
  <div class="insight-query-fields">
    <Select label="Reporting settings" value={state.draftQuery.playbook_id ?? ''} options={[{ value: '', label: 'All reporting settings' }, ...state.reportingOptions.map((setting): SelectOption => ({ value: setting.id, label: setting.name }))]} onchange={(value: string): void => state.filter('playbook_id', value)} />
    <Select label="Pattern" value={state.draftQuery.pattern_id ?? ''} options={[{ value: '', label: 'All patterns' }, ...state.patterns.map((pattern): SelectOption => ({ value: pattern.id, label: pattern.name }))]} onchange={(value: string): void => state.filter('pattern_id', value)} />
    <Select label="Status" value={state.draftQuery.status ?? ''} options={[{ value: '', label: 'All statuses' }, ...Object.entries(reportStatuses).map(([value, label]): SelectOption => ({ value, label }))]} onchange={(value: string): void => state.filter('status', value)} />
  </div>
</QueryPanel>
{#if state.message}<p role="status">{state.message}</p>{/if}
{#if state.busy || state.hasResult}
<section class="insight-results" aria-label="Entries" aria-busy={state.busy}>
  {#if state.busy}<p class="insight-caption" role="status">Loading entries…</p>
  {:else}
    <div class="insight-result-meta"><span>{state.page.total} {state.page.total === 1 ? 'entry' : 'entries'}</span></div>
    {#each state.page.items as report (report.report_id)}
      <a class="report-row" href={`${listHref}?report=${encodeURIComponent(report.report_id)}`}><strong>{state.reportingName(report.playbook_id)}</strong><span>{report.observed_pattern_ids.map(state.patternName).join(', ') || 'No patterns observed'}</span><DateTimeView value={report.received_at} /><span>Agent-reported trigger: {report.trigger === 'proactive' ? 'proactive' : 'user requested'}</span></a>
    {:else}<p class="insight-caption">No entries match this query.</p>{/each}
    <div class="insight-pagination"><Button disabled={state.query.offset === 0} onclick={(): void => state.paginate(-1)}>Previous</Button><span>Page {state.pageNumber}</span><Button disabled={!state.hasNext} onclick={(): void => state.paginate(1)}>Next</Button></div>
  {/if}
</section>
{/if}
<style>
  .report-row { display: flex; gap: .5rem 1rem; justify-content: space-between; flex-wrap: wrap; overflow-wrap: anywhere; margin-bottom: 12px; padding: 1rem; color: inherit; text-decoration: none; border: 1px solid var(--admin-border); border-radius: 8px; }
  .report-row:hover, .report-row:focus-visible { background: var(--admin-soft); border-color: var(--admin-accent); }
</style>
