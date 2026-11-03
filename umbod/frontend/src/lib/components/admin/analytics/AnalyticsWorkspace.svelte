<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
  import { dimensions } from '$lib/admin/analytics/domain/schemas';
  import { bucketOptions, dimensionLabels, rangeOptions } from '$lib/admin/analytics/query-draft.svelte';
  import Button from '../shared/Button.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import Select from '../shared/Select.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';

  let { state }: { state: AnalyticsState } = $props();
  onDestroy(() => state.dispose());
</script>

<header>
  <h1 class="admin-title">Log analytics</h1>
  <p class="admin-lede">Count ingested telemetry logs across your instance. Filter exact values, combine dimensions, and explore activity over time.</p>
  <p class="hint">Includes accepted OTLP log exports, not application stdout, metrics, or traces. Configure clients to export logs to this instance’s authenticated /v1/logs receiver.</p>
</header>

{#if state.accessLost}
  <div class="admin-message admin-message--error" role="alert">{state.error}</div>
{:else}
  <form id="analytics-query" class="admin-panel query" onsubmit={(event) => { event.preventDefault(); void state.run(); }}>
    <div class="section-heading"><h2>Build a query</h2><span>Run when you’re ready · no automatic refresh</span></div>
    <div class="range-grid">
      <Select label="Time range" options={rangeOptions} value={state.draft.preset} onchange={(value) => state.draft.setPreset(value)} />
      <Select label="Time buckets" options={bucketOptions} value={state.draft.bucket} onchange={(value) => state.draft.setBucket(value)} />
      <label class="field" for="analytics-limit">Maximum groups<input id="analytics-limit" type="number" min="1" max="1000" step="1" required value={state.draft.limit} oninput={(event) => state.draft.setLimit(event.currentTarget.value)} /><small>1–1,000; excess groups return an error, never a partial total.</small></label>
    </div>
    {#if state.draft.preset === 'custom'}
      <div class="range-grid">
        <label class="field" for="analytics-start">Start (inclusive)<input id="analytics-start" type="datetime-local" step="1" required value={state.draft.start} oninput={(event) => state.draft.setStart(event.currentTarget.value)} /></label>
        <label class="field" for="analytics-end">End (exclusive)<input id="analytics-end" type="datetime-local" step="1" required value={state.draft.end} oninput={(event) => state.draft.setEnd(event.currentTarget.value)} /></label>
        <label class="field" for="analytics-offset">UTC offset<input id="analytics-offset" type="text" required placeholder="+00:00" value={state.draft.offset} oninput={(event) => state.draft.setOffset(event.currentTarget.value)} /><small>Fixed offset for both dates, not browser local time. Use separate queries across daylight-saving changes.</small></label>
      </div>
    {/if}
    <p class="hint">Preset ranges end at execution time. All results use UTC and include the start, but exclude the end.</p>
    <fieldset>
      <legend>Group by</legend>
      <p class="hint">Select dimensions in order. Leave all unchecked for a single total.</p>
      <div class="choices">
        {#each dimensions as dimension (dimension)}
          <label class="choice"><input type="checkbox" checked={state.draft.groupBy.includes(dimension)} onchange={() => state.draft.toggleGroup(dimension)} />{dimensionLabels[dimension]}</label>
        {/each}
      </div>
      {#if state.draft.groupBy.length > 0}
        <ol class="group-order" aria-label="Grouping order">
          {#each state.draft.groupBy as dimension, index (dimension)}
            <li><span>{index + 1}. {dimensionLabels[dimension]}</span><Button variant="quiet" size="compact" aria-label={`Move ${dimensionLabels[dimension]} earlier`} disabled={index === 0} onclick={() => state.draft.moveGroup(dimension, -1)}>↑</Button><Button variant="quiet" size="compact" aria-label={`Move ${dimensionLabels[dimension]} later`} disabled={index === state.draft.groupBy.length - 1} onclick={() => state.draft.moveGroup(dimension, 1)}>↓</Button></li>
          {/each}
        </ol>
      {/if}
    </fieldset>
    <fieldset>
      <legend>Exact-match filters</legend>
      <p class="hint" id="filter-help">Add one value at a time. Values within a dimension use OR; dimensions use AND. Case and spaces are preserved. Add a blank input to match an empty string; missing attributes cannot be filtered.</p>
      <div class="filters">
        {#each dimensions as dimension (dimension)}
          <div class="filter">
            <label for={`analytics-filter-${dimension}`}>{dimensionLabels[dimension]}</label>
            <div class="filter-entry"><input id={`analytics-filter-${dimension}`} type="text" aria-describedby="filter-help" value={state.draft.inputs[dimension]} oninput={(event) => state.draft.setInput(dimension, event.currentTarget.value)} onkeydown={(event) => { if (event.key === 'Enter') { event.preventDefault(); state.draft.addFilter(dimension); } }} /><Button variant="secondary" size="compact" aria-label={`Add ${dimensionLabels[dimension]} value`} onclick={() => state.draft.addFilter(dimension)}>Add</Button></div>
            <ul class="values" aria-label={`${dimensionLabels[dimension]} filters`}>
              {#each state.draft.filters[dimension] as value (value)}
                <li><code>{value === '' ? '(empty string)' : JSON.stringify(value)}</code><Button variant="quiet" size="compact" aria-label={`Remove ${dimensionLabels[dimension]} value ${JSON.stringify(value)}`} onclick={() => state.draft.removeFilter(dimension, value)}>×</Button></li>
              {/each}
            </ul>
          </div>
        {/each}
      </div>
    </fieldset>
    {#if state.validation}<div class="admin-message admin-message--error" role="alert">{state.validation}</div>{/if}
    <div class="actions"><LoadingButton type="submit" label="Run query" loadingLabel="Running query" loading={state.pending} /><span role="status">{state.pending ? 'Query in progress. Draft changes will not affect this request.' : state.changed ? 'Draft changed — run query to apply.' : 'Ready to query'}</span></div>
  </form>
  {#if state.error}
    <div class="admin-message admin-message--error failure" role="alert"><span>{state.error}</span><Button variant="secondary" disabled={state.pending} onclick={() => state.run()}>Retry query</Button></div>
  {/if}
  {#if state.result}
    <section class="admin-panel results" aria-label="Query results" aria-busy={state.pending}>
      <div class="section-heading"><h2>Results</h2><span>{state.changed ? 'Last successful query · draft not applied' : 'Last successful query'}</span></div>
      <p class="range"><DateTimeView value={state.result.query.time_range.start} /> → <DateTimeView value={state.result.query.time_range.end} /> (exclusive)</p>
      <p class="hint">{state.groupingLabel} · {state.bucketLabel} · Maximum {state.result.query.max_groups} groups</p>
      {#if state.result.query.filters.length > 0}<ul class="submitted-filters">{#each state.result.query.filters as filter (filter.dimension)}<li>{dimensionLabels[filter.dimension]}: {filter.values.map((value) => JSON.stringify(value)).join(' OR ')}</li>{/each}</ul>{:else}<p class="hint">No filters · all instance logs in this range</p>{/if}
      <dl class="stats"><div><dt>Matching logs</dt><dd>{state.total.toLocaleString('en')}</dd></div><div><dt>Observed groups</dt><dd>{state.groupCount.toLocaleString('en')}</dd></div><div><dt>Result rows</dt><dd>{state.result.response.rows.length.toLocaleString('en')}</dd></div></dl>
      {#if state.result.response.rows.length === 0}
        <p class="empty" role="status">No logs matched this query. Try a wider time range or fewer filters.</p>
      {:else}
        <p class="hint table-hint">Scroll horizontally to view all dimensions. Log counts stay visible.</p>
        <div class="table-scroll" role="region" aria-label="Log-count results table">
          <table><caption>Observed groups and buckets only; absent time buckets are not zero-filled. <a href="#analytics-query">Edit query</a></caption><thead><tr>{#if state.result.query.bucketing.kind === 'fixed'}<th scope="col">Bucket start (UTC)</th>{/if}{#each state.result.query.group_by as dimension (dimension)}<th scope="col">{dimensionLabels[dimension]}</th>{/each}<th scope="col" class="count">Log count</th></tr></thead><tbody>
            {#each state.tableRows as row (JSON.stringify([row.bucket, row.groups]))}
              <tr>{#if row.bucket.kind === 'bucket'}<td><DateTimeView value={row.bucket.start} /></td>{/if}{#each row.groups as group (group.dimension)}<td>{#if group.value.kind === 'missing'}<span class="missing">Missing attribute</span>{:else if group.value.value === ''}<span class="missing">Empty string</span>{:else}<code>{JSON.stringify(group.value.value)}</code>{/if}</td>{/each}<td class="count">{row.count.toLocaleString('en')}</td></tr>
            {/each}
          </tbody></table>
        </div>
      {/if}
    </section>
  {:else if !state.pending && !state.error}
    <div class="admin-panel empty">Choose your range and dimensions, then run a query to explore log counts.</div>
  {/if}
{/if}

<style>
  header { margin-bottom: 1.5rem; }
  .query, .results { padding: 1.5rem; margin-bottom: 1.25rem; display: grid; gap: 1rem; }
  .section-heading, .actions, .failure { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem; }
  h2 { font-size: 1.05rem; margin: 0; }
  .section-heading > span, .actions > span, .hint, small { font-size: .8125rem; color: var(--admin-muted); }
  .range-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; align-items: start; }
  .field, .filter { display: grid; gap: .35rem; min-width: 0; }
  label, legend { font-size: .8125rem; font-weight: 600; }
  input:not([type='checkbox']) { min-width: 0; width: 100%; box-sizing: border-box; min-height: 2.75rem; border: 1px solid var(--admin-border); border-radius: 6px; padding: .65rem .7rem; color: var(--admin-ink); background: var(--admin-panel); font: inherit; }
  small { font-weight: 400; }
  fieldset { border: 0; border-top: 1px solid var(--admin-border); margin: 0; padding: 1rem 0 0; min-width: 0; }
  legend { padding-right: .75rem; }
  .hint { margin: 0; line-height: 1.6; }
  fieldset > .hint { margin-bottom: .75rem; }
  .choices { display: flex; flex-wrap: wrap; gap: .5rem 1.25rem; }
  .choice { display: flex; gap: .5rem; align-items: center; min-height: 2rem; }
  .group-order, .values { display: flex; gap: .5rem; flex-wrap: wrap; list-style: none; padding: 0; margin: .5rem 0 0; }
  .group-order li, .values li { display: flex; align-items: center; background: var(--admin-soft); border-radius: 6px; padding-left: .6rem; min-width: 0; }
  .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1rem; }
  .filter { align-content: start; }
  .filter-entry { display: flex; gap: .35rem; align-items: center; }
  .values { margin: 0; }
  code { white-space: pre-wrap; overflow-wrap: anywhere; font-size: .8125rem; }
  .failure { margin-bottom: 1.25rem; }
  .range { font-size: .875rem; margin: 0; }
  .submitted-filters { margin: 0; padding-left: 1.25rem; font-size: .8125rem; overflow-wrap: anywhere; white-space: pre-wrap; }
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: .25rem 0; }
  .stats div { padding: 1rem; background: var(--admin-soft); border-radius: 8px; }
  dt { font-size: .8125rem; color: var(--admin-muted); }
  dd { font-size: 1.65rem; font-weight: 600; margin: .35rem 0 0; font-variant-numeric: tabular-nums; }
  .empty { text-align: center; color: var(--admin-muted); padding: 2rem; }
  .table-scroll { overflow: auto; max-height: 36rem; border: 1px solid var(--admin-border); border-radius: 8px; }
  table { border-collapse: collapse; width: 100%; text-align: left; font-size: .875rem; }
  caption { caption-side: bottom; text-align: left; padding: .75rem; font-size: .75rem; color: var(--admin-muted); }
  caption a { color: var(--admin-accent); white-space: nowrap; }
  th, td { padding: .75rem 1rem; border-bottom: 1px solid var(--admin-border); overflow-wrap: anywhere; min-width: 7rem; }
  th { background: var(--admin-soft); position: sticky; top: 0; font-size: .75rem; }
  .count { min-width: 5rem; text-align: right; font-variant-numeric: tabular-nums; position: sticky; right: 0; background: var(--admin-panel); }
  th.count { background: var(--admin-soft); z-index: 2; }
  .table-hint { display: none; }
  .missing { color: var(--admin-muted); font-style: italic; }
  @media (max-width: 700px) { .table-hint { display: block; } .range-grid { grid-template-columns: 1fr; } .query, .results { padding: 1rem; } .stats { gap: .5rem; } .stats div { padding: .65rem; } dd { font-size: 1.25rem; } }
</style>
