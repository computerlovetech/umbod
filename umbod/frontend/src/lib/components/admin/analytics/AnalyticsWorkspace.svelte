<script lang="ts">
  import { onDestroy } from 'svelte';
  import type { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
  import { dimensions } from '$lib/admin/analytics/domain/schemas';
  import { bucketOptions, dimensionLabels, dimensionOptions, rangeOptions } from '$lib/admin/analytics/query-draft.svelte';
  import Button from '../shared/Button.svelte';
  import LoadingButton from '../shared/LoadingButton.svelte';
  import Select from '../shared/Select.svelte';
  import DateTimeView from '$lib/components/shared/DateTimeView.svelte';

  let { state }: { state: AnalyticsState } = $props();
  onDestroy(() => state.dispose());
</script>

<header>
  <h1 class="admin-title">Log analytics</h1>
  <p class="admin-lede">Explore log activity across your instance.</p>
</header>

{#if state.accessLost}
  <div class="admin-message admin-message--error" role="alert">{state.error}</div>
{:else}
  <form id="analytics-query" class="admin-panel query" novalidate onsubmit={(event) => { event.preventDefault(); void state.run(); }}>
    <div class="toolbar">
      <Select label="Time range" options={rangeOptions} value={state.draft.preset} onchange={(value) => state.draft.setPreset(value)} />
      <Select label="Interval" options={bucketOptions} value={state.draft.bucket} onchange={(value) => state.draft.setBucket(value)} />
      <LoadingButton type="submit" label="Run query" loadingLabel="Running query" loading={state.pending} />
    </div>
    {#if state.draft.preset === 'custom'}
      <div class="range-grid">
        <label class="field" for="analytics-start">Start<input id="analytics-start" type="datetime-local" step="1" required value={state.draft.start} oninput={(event) => state.draft.setStart(event.currentTarget.value)} /></label>
        <label class="field" for="analytics-end">End<input id="analytics-end" type="datetime-local" step="1" required value={state.draft.end} oninput={(event) => state.draft.setEnd(event.currentTarget.value)} /></label>
        <label class="field" for="analytics-offset">UTC offset<input id="analytics-offset" type="text" required placeholder="+00:00" value={state.draft.offset} oninput={(event) => state.draft.setOffset(event.currentTarget.value)} /></label>
      </div>
    {/if}
    <fieldset class="grouping">
      <legend>Group by</legend>
      <div class="choices">
        {#each dimensions as dimension (dimension)}
          <label class="choice"><input type="checkbox" checked={state.draft.groupBy.includes(dimension)} onchange={() => state.draft.toggleGroup(dimension)} />{dimensionLabels[dimension]}</label>
        {/each}
      </div>
    </fieldset>
    <div class="filter-bar">
      <span class="filter-label">Filters</span>
      <ul class="values" aria-label="Selected filters">
        {#each dimensions as dimension (dimension)}
          {#each state.draft.filters[dimension] as value (value)}
            <li><span>{dimensionLabels[dimension]}: <strong class="exact-value">{value === '' ? 'Empty value' : value}</strong></span><Button variant="quiet" size="compact" aria-label={`Remove ${dimensionLabels[dimension]} value ${JSON.stringify(value)}`} onclick={() => state.draft.removeFilter(dimension, value)}>×</Button></li>
          {/each}
        {/each}
      </ul>
      <Button variant="secondary" size="compact" aria-expanded={state.choices.open} aria-controls="analytics-filter-picker" onclick={() => state.choices.open ? state.choices.close() : state.choices.show()}>{state.choices.open ? 'Close filters' : '+ Add filter'}</Button>
    </div>
    {#if state.choices.open}
      <section id="analytics-filter-picker" class="filter-picker" aria-label="Add a filter">
        <div class="picker-fields">
          <Select label="Filter by" options={dimensionOptions} value={state.choices.dimension} onchange={(value) => { void state.choices.setDimension(value); }} />
          <Select label="Choose a value" options={state.choices.options} value="" onchange={(value) => state.choices.choose(value)} disabled={Boolean(state.choices.pending) || state.choices.stale || Boolean(state.choices.error)} search={{ value: state.choices.search, oninput: state.choices.setSearch, placeholder: state.choices.pending ? 'Loading values…' : 'Search log values…' }} emptyMessage={state.choices.emptyMessage} />
        </div>
        {#if state.choices.pending}
          <p class="hint" role="status">Loading log values…</p>
        {:else if state.choices.error}
          <div class="picker-feedback" role="alert"><span>{state.choices.error}</span><Button variant="secondary" size="compact" onclick={() => state.choices.refresh()}>Retry values</Button></div>
        {:else if state.choices.stale}
          <div class="picker-feedback" role="status"><span>Time range changed.</span><Button variant="secondary" size="compact" onclick={() => state.choices.refresh()}>Refresh values</Button></div>
        {:else}
          <p class="hint">Values from this time range, before filters.</p>
        {/if}
      </section>
    {/if}
    {#if state.validation}<div class="admin-message admin-message--error" role="alert">{state.validation}</div>{/if}
    {#if state.pending || state.changed}<p class="hint" role="status">{state.pending ? 'Running query…' : 'Filters or settings changed. Run query to update results.'}</p>{/if}
  </form>
  {#if state.error}
    <div class="admin-message admin-message--error failure" role="alert"><span>{state.error}</span><Button variant="secondary" disabled={state.pending} onclick={() => state.retry()}>Retry query</Button></div>
  {/if}
  {#if state.result}
    <section class="admin-panel results" aria-label="Query results" aria-busy={state.pending}>
      <div class="section-heading"><h2>Results</h2>{#if state.changed}<span>Previous query</span>{/if}</div>
      <p class="range"><DateTimeView value={state.result.query.time_range.start} /> → <DateTimeView value={state.result.query.time_range.end} /></p>
      {#if state.result.query.filters.length > 0}<ul class="submitted-filters">{#each state.result.query.filters as filter (filter.dimension)}<li>{dimensionLabels[filter.dimension]}: {filter.values.map((value) => value === '' ? 'Empty value' : value).join(', ')}</li>{/each}</ul>{/if}
      <dl class="stats"><div><dt>Logs on this page</dt><dd>{state.total.toLocaleString('en')}</dd></div><div><dt>Groups on this page</dt><dd>{state.groupCount.toLocaleString('en')}</dd></div></dl>
      {#if state.result.response.rows.length === 0}
        <p class="empty" role="status">No logs on this page. Try a wider time range or fewer filters.</p>
      {:else}
        <div class="table-scroll" role="region" aria-label="Log-count results table">
          <table><caption><a href="#analytics-query">Edit query</a> · {state.groupingLabel} · {state.bucketLabel} · Page {state.page}. Only observed groups and time buckets are shown.</caption><thead><tr>{#if state.result.query.bucketing.kind === 'fixed'}<th scope="col">Bucket start (UTC)</th>{/if}{#each state.result.query.group_by as dimension (dimension)}<th scope="col">{dimensionLabels[dimension]}</th>{/each}<th scope="col" class="count">Log count</th></tr></thead><tbody>
            {#each state.tableRows as row (JSON.stringify([row.bucket, row.groups]))}
              <tr>{#if row.bucket.kind === 'bucket'}<td><DateTimeView value={row.bucket.start} /></td>{/if}{#each row.groups as group (group.dimension)}<td>{#if group.value.kind === 'missing'}<span class="missing">Missing attribute</span>{:else if group.value.value === ''}<span class="missing">Empty string</span>{:else}<span class="exact-value">{group.value.value}</span>{/if}</td>{/each}<td class="count">{row.count.toLocaleString('en')}</td></tr>
            {/each}
          </tbody></table>
        </div>
      {/if}
      <nav class="pagination" aria-label="Results pagination">
        <Button variant="secondary" disabled={!state.canGoPrevious} onclick={() => state.previous()}>Previous</Button>
        <span aria-live="polite">Page {state.page}</span>
        <Button variant="secondary" disabled={!state.canGoNext} onclick={() => state.next()}>Next</Button>
      </nav>
    </section>
  {:else if !state.pending && !state.error}
    <div class="admin-panel empty">Run a query to see log activity.</div>
  {/if}
{/if}

<style>
  header { margin-bottom: 1.5rem; }
  .query, .results { padding: 1.5rem; margin-bottom: 1.25rem; display: grid; gap: 1.25rem; }
  .toolbar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; gap: 1rem; align-items: end; }
  .section-heading, .failure, .picker-feedback { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem; }
  h2 { font-size: 1.05rem; margin: 0; }
  .section-heading > span, .hint, .picker-feedback { font-size: .8125rem; color: var(--admin-muted); }
  .range-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1rem; align-items: start; }
  .field { display: grid; gap: .35rem; min-width: 0; }
  label, legend, .filter-label { font-size: .8125rem; font-weight: 600; }
  input:not([type='checkbox']) { min-width: 0; width: 100%; box-sizing: border-box; min-height: 2.75rem; border: 1px solid var(--admin-border); border-radius: 6px; padding: .65rem .7rem; color: var(--admin-ink); background: var(--admin-panel); font: inherit; }
  fieldset { border: 0; margin: 0; padding: 0; min-width: 0; }
  legend { padding: 0; margin-bottom: .35rem; }
  .hint { margin: 0; line-height: 1.6; }
  .choices { display: flex; flex-wrap: wrap; gap: .5rem 1.25rem; }
  .choice { display: flex; gap: .5rem; align-items: center; min-height: 2rem; }
  .filter-bar { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem; border-top: 1px solid var(--admin-border); padding-top: 1rem; }
  .values { display: flex; gap: .5rem; flex-wrap: wrap; list-style: none; padding: 0; margin: 0; min-width: 0; }
  .values li { display: flex; align-items: center; background: var(--admin-soft); border-radius: 6px; padding-left: .6rem; min-width: 0; max-width: 100%; font-size: .8125rem; }
  .values li > span { overflow-wrap: anywhere; min-width: 0; }
  .exact-value { white-space: pre-wrap; overflow-wrap: anywhere; }
  .filter-picker { display: grid; gap: .75rem; padding: 1rem; border: 1px solid var(--admin-border); border-radius: 8px; background: var(--admin-soft); }
  .picker-fields { display: grid; grid-template-columns: minmax(9rem, 1fr) minmax(0, 2fr); gap: 1rem; }
  .failure { margin-bottom: 1.25rem; }
  .range { font-size: .8125rem; color: var(--admin-muted); margin: 0; }
  .submitted-filters { margin: 0; padding-left: 1.25rem; font-size: .8125rem; overflow-wrap: anywhere; white-space: pre-wrap; }
  .stats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem; margin: 0; }
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
  .missing { color: var(--admin-muted); font-style: italic; }
  .pagination { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: .75rem; }
  .pagination span { color: var(--admin-muted); font-size: .875rem; }
  @media (max-width: 700px) { .toolbar, .range-grid, .picker-fields { grid-template-columns: 1fr; } .query, .results { padding: 1rem; } .stats { gap: .5rem; } .stats div { padding: .65rem; } dd { font-size: 1.25rem; } }
</style>
