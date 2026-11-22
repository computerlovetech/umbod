<script lang="ts">
  import { onMount, onDestroy, type Snippet } from 'svelte';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import Select from '#lib/components/admin/shared/Select.svelte';
  import type { SelectOption } from '#lib/components/admin/shared/select-state.svelte.js';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import QueryPanel from '#lib/components/shared/workspace/QueryPanel.svelte';
  import type { ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  let { state, detailActions, detailCloseDisabled = false }: {
    state: ReportsState;
    detailActions?: Snippet;
    detailCloseDisabled?: boolean;
  } = $props();
  const statuses = { observed: 'Observed', not_observed: 'Not observed', not_assessed: 'Not assessed' };
  onMount((): void => state.start());
  onDestroy((): void => state.stop());
</script>

<QueryPanel id="agent-behaviour-query" summary={state.querySummary} pending={state.busy} onrun={state.runQuery} onreset={state.resetQuery}>
  <div class="insight-query-fields">
    <Select label="Reporting settings" value={state.draftQuery.playbook_id ?? ''} options={[{ value: '', label: 'All reporting settings' }, ...state.reportingOptions.map((setting): SelectOption => ({ value: setting.id, label: setting.name }))]} onchange={(value: string): void => state.filter('playbook_id', value)} />
    <Select label="Pattern" value={state.draftQuery.pattern_id ?? ''} options={[{ value: '', label: 'All patterns' }, ...state.patterns.map((pattern): SelectOption => ({ value: pattern.id, label: pattern.name }))]} onchange={(value: string): void => state.filter('pattern_id', value)} />
    <Select label="Status" value={state.draftQuery.status ?? ''} options={[{ value: '', label: 'All statuses' }, ...Object.entries(statuses).map(([value, label]): SelectOption => ({ value, label }))]} onchange={(value: string): void => state.filter('status', value)} />
  </div>
</QueryPanel>
{#if state.message}<p role="status">{state.message}</p>{/if}
{#if state.busy || state.hasResult}
<section class="insight-results" aria-label="Entries" aria-busy={state.busy}>
  {#if state.busy}<p class="insight-caption" role="status">Loading entries…</p>
  {:else}
    <div class="insight-result-meta"><span>{state.page.total} {state.page.total === 1 ? 'entry' : 'entries'}</span></div>
    {#each state.page.items as report (report.report_id)}
      <Button variant="secondary" class="report-row" onclick={(): void => { void state.open(report.report_id); }}><span>{state.reportingName(report.playbook_id)}</span><span>{report.observed_pattern_ids.map(state.patternName).join(', ') || 'No patterns observed'}</span><DateTimeView value={report.received_at} /><span>{report.trigger === 'proactive' ? 'Proactive' : 'User requested'}</span></Button>
    {:else}<p class="insight-caption">No entries match this query.</p>{/each}
    <div class="insight-pagination"><Button disabled={state.query.offset === 0} onclick={(): void => state.paginate(-1)}>Previous</Button><span>Page {state.pageNumber}</span><Button disabled={!state.hasNext} onclick={(): void => state.paginate(1)}>Next</Button></div>
  {/if}
</section>
{/if}
{#if state.detailBusy}<p role="status">Loading…</p>{/if}
{#if state.detail}
  <ModalShell title={state.detail.instructions.playbook.name} titleId="entry-detail-title" close={state.close} closeDisabled={state.detailBusy || detailCloseDisabled} --modal-overflow="auto">
  <section class="detail" aria-label="Entry detail">
    <p>Agent self-reported · Not independently verified</p>
    {#each state.assessments as assessment (assessment.pattern_id)}
      {@const pattern = assessment.pattern}
      <article>
        <h3>{pattern?.name ?? 'Removed pattern'} · <span data-status={assessment.status}>{statuses[assessment.status]}</span></h3>
        <p class="prose">{assessment.summary}</p>
        <h4>Factual evidence</h4><ul>{#each assessment.evidence as evidence, index (index)}<li class="prose">{evidence}</li>{:else}<li>No evidence supplied</li>{/each}</ul>
        {#if pattern}
          <details><summary>Original pattern criteria</summary>
            <p class="prose">{pattern.description}</p><h4>Assessment prompt</h4><p class="prose">{pattern.assessment_prompt}</p>
            <h4>Inclusion criteria</h4><p class="prose">{pattern.inclusion_criteria || 'None'}</p>
            <h4>Exclusion criteria</h4><p class="prose">{pattern.exclusion_criteria || 'None'}</p>
            <p>Polarity: {pattern.polarity} · Categories: {pattern.categories.join(', ') || 'None'}</p>
          </details>
        {/if}
      </article>
    {/each}
    <details>
      <summary>Technical details</summary>
      <dl>
      <dt>Report ID</dt><dd>{state.detail.report_id}</dd>
      <dt>Received</dt><dd><DateTimeView value={state.detail.received_at} /></dd>
      <dt>Expires</dt><dd><DateTimeView value={state.detail.expires_at} /></dd>
      <dt>Caller</dt><dd>{'subject' in state.detail.caller.subject ? state.detail.caller.subject.subject : 'Unavailable'}</dd>
      <dt>Issuer</dt><dd>{'issuer' in state.detail.caller.subject && 'value' in state.detail.caller.subject.issuer ? state.detail.caller.subject.issuer.value : 'Unavailable'}</dd>
      <dt>Authentication</dt><dd>{state.detail.caller.authentication}</dd>
      <dt>Trigger (caller assertion)</dt><dd>{state.detail.submission.trigger === 'proactive' ? 'Proactive' : 'User requested'}</dd>
      <dt>Original configuration revision</dt><dd>{state.detail.instructions.configuration_revision}</dd>
    </dl>
    <h3>Original collection instructions</h3><p class="prose">{state.detail.instructions.playbook.collection_instructions}</p>
    <h3>Original reporting guidance</h3><p class="prose">{state.detail.instructions.reporting_guidance}</p>
    </details>
    {@render detailActions?.()}
  </section>
  </ModalShell>
{/if}

<style>
  :global(.report-row) { width: 100%; text-align: left; display: flex; gap: 1rem; justify-content: space-between; flex-wrap: wrap; margin-bottom: 12px; padding: 18px; }
  .detail, article { border: 1px solid var(--admin-border); border-radius: var(--admin-radius); padding: 1rem; margin: 1rem 0; overflow-wrap: anywhere; }
  .prose { white-space: pre-wrap; overflow-wrap: anywhere; }
  dt { font-weight: 600; margin-top: .6rem; } dd { margin: .25rem 0; }
  [data-status] { border: 1px solid currentColor; border-radius: .3rem; padding: .15rem .4rem; }
  [data-status='observed'] { color: var(--admin-accent); }
</style>
