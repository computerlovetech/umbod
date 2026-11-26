<script lang="ts">
  import { onMount, onDestroy, type Snippet } from 'svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import { reportStatuses, type ReportsState } from '#lib/agent-behaviour/state/reports-state.svelte.js';

  let { state, reportId, listHref, actions }: {
    state: ReportsState; reportId: string; listHref: string; actions?: Snippet;
  } = $props();
  const statuses = ['observed', 'not_assessed', 'not_observed'] as const;
  onMount((): void => { void state.open(reportId); });
  onDestroy((): void => state.close());

  function restorePatternLink(article: HTMLElement): void {
    if (window.location.hash !== `#${article.id}`) return;
    article.focus({ preventScroll: true });
    article.scrollIntoView({ block: 'start' });
  }
</script>

<a class="admin-back-link" href={listHref}>← Back to reports</a>
{#if state.detail}
  {@const report = state.detail}
  {@const assessments = state.assessments}
  {@const counts = state.assessmentCounts}
  <section class="report" aria-labelledby="report-heading">
    <header>
      <h2 id="report-heading">{report.instructions.playbook.name}</h2>
      <p class="meta"><DateTimeView value={report.received_at} /> · Agent-reported trigger: {report.submission.trigger === 'proactive' ? 'proactive' : 'user requested'}</p>
      <p class="provenance">Agent self-reported · Not independently verified</p>
      <ul class="counts" aria-label="Assessment summary">
        {#each statuses as status (status)}
          <li class="badge" data-status={status}>{counts[status]} {reportStatuses[status].toLowerCase()}</li>
        {/each}
      </ul>
    </header>
    <div class="indexed-report">
      <nav aria-label="Patterns in this report">
        <h3>Patterns</h3>
        <ul>
          {#each assessments as assessment (assessment.pattern_id)}
            <li><a href={`#pattern-${assessment.pattern_id}`}>{assessment.pattern?.name ?? assessment.pattern_id}</a><span class="badge" data-status={assessment.status}>{reportStatuses[assessment.status]}</span></li>
          {/each}
        </ul>
      </nav>
      <div class="assessments">
        {#each assessments as assessment (assessment.pattern_id)}
          {@const pattern = assessment.pattern}
          <article id={`pattern-${assessment.pattern_id}`} data-status={assessment.status} tabindex="-1" {@attach restorePatternLink}>
            <header class="assessment-heading"><h3>{pattern?.name ?? assessment.pattern_id}</h3><span class="badge" data-status={assessment.status}>{reportStatuses[assessment.status]}</span></header>
            {#if assessment.summary}<p class="prose">{assessment.summary}</p>{/if}
            {#if assessment.evidence.length}
              <h4>Reported evidence</h4>
              <ul class="evidence">{#each assessment.evidence as evidence, index (index)}<li class="prose">{evidence}</li>{/each}</ul>
            {/if}
            {#if pattern}
              <details class="criteria"><summary>View original criteria</summary>
                <p class="prose">{pattern.description}</p>
                <dl>
                  {#if pattern.assessment_prompt !== pattern.description}<dt>Assessment prompt</dt><dd class="prose">{pattern.assessment_prompt}</dd>{/if}
                  <dt>Inclusion criteria</dt><dd class="prose">{pattern.inclusion_criteria || 'None'}</dd>
                  <dt>Exclusion criteria</dt><dd class="prose">{pattern.exclusion_criteria || 'None'}</dd>
                  <dt>Polarity</dt><dd>{pattern.polarity}</dd>
                  <dt>Categories</dt><dd>{pattern.categories.join(', ') || 'None'}</dd>
                </dl>
              </details>
            {/if}
          </article>
        {/each}
      </div>
    </div>
    <section class="technical" aria-labelledby="technical-heading">
      <h3 id="technical-heading">Technical details</h3>
      <dl class="technical-facts technical-overview">
        <div><dt>Report ID</dt><dd><code>{report.report_id}</code></dd></div>
        <div><dt>Expires</dt><dd><DateTimeView value={report.expires_at} /></dd></div>
        <div><dt>Original configuration revision</dt><dd>{report.instructions.configuration_revision}</dd></div>
      </dl>
      <details>
        <summary>Caller and authentication</summary>
        <dl class="technical-facts">
          <div><dt>Caller</dt><dd>{'subject' in report.caller.subject ? report.caller.subject.subject : 'Unavailable'}</dd></div>
          <div><dt>Issuer</dt><dd>{'issuer' in report.caller.subject && 'value' in report.caller.subject.issuer ? report.caller.subject.issuer.value : 'Unavailable'}</dd></div>
          <div><dt>Authentication</dt><dd>{report.caller.authentication}</dd></div>
        </dl>
      </details>
      <details>
        <summary>Original collection instructions</summary>
        <p class="prose technical-text">{report.instructions.playbook.collection_instructions}</p>
      </details>
      <details>
        <summary>Original reporting guidance</summary>
        <p class="prose technical-text">{report.instructions.reporting_guidance}</p>
      </details>
    </section>
    {#if actions}<footer>{@render actions()}</footer>{/if}
  </section>
{/if}
{#if state.message}<p role="status">{state.message}</p>
{:else if !state.detail}<p role="status">Loading report…</p>{/if}

<style>
  .report { container-type: inline-size; background: var(--admin-panel); border: 1px solid var(--admin-border); border-radius: 12px; padding: clamp(1rem, 3vw, 2rem); overflow-wrap: anywhere; }
  h2, h3, h4, p { margin: 0; }
  h2 { font-size: clamp(1.6rem, 4vw, 2.1rem); line-height: 1.15; }
  h3 { font-size: 1rem; }
  h4 { font-size: .875rem; margin-top: .8rem; }
  .meta, .provenance { color: var(--admin-muted); font-size: .875rem; margin-top: .45rem; }
  .counts, nav ul { padding: 0; list-style: none; }
  .counts { display: flex; flex-wrap: wrap; gap: .4rem; margin: 1rem 0 0; }
  .badge { display: inline-block; width: fit-content; padding: .15rem .5rem; border-radius: 999px; background: var(--admin-accent-soft); color: var(--admin-accent); font-size: .75rem; font-weight: 650; }
  .badge[data-status='observed'] { background: var(--admin-warning-bg); color: var(--admin-warning-text); }
  .badge[data-status='not_assessed'] { background: var(--admin-soft); color: var(--admin-muted); }
  .indexed-report { display: grid; grid-template-columns: minmax(0, 1fr) minmax(11rem, 15rem); gap: 1rem; margin-top: 1.25rem; }
  nav { grid-column: 2; grid-row: 1; align-self: start; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 8px; padding: .85rem; }
  nav ul { margin: .5rem 0 0; }
  nav li { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: .25rem .45rem; border-top: 1px solid var(--admin-border); padding: .45rem 0; font-size: .84rem; }
  nav a { color: var(--admin-accent); text-underline-offset: .15em; }
  .assessments { grid-column: 1; grid-row: 1; display: grid; gap: .75rem; min-width: 0; }
  article { border: 1px solid var(--admin-border); border-radius: 8px; padding: .85rem 1rem; scroll-margin-top: 1rem; }
  article[data-status='observed'] { border-inline-start: 4px solid var(--admin-warning-border); }
  article:target { outline: 2px solid var(--admin-accent); outline-offset: 2px; }
  .assessment-heading { display: flex; align-items: baseline; justify-content: space-between; gap: .5rem; flex-wrap: wrap; }
  .prose { white-space: pre-wrap; margin-top: .45rem; }
  .evidence { margin: .25rem 0 0; padding-left: 1.15rem; }
  details { margin-top: .75rem; border-top: 1px solid var(--admin-border); padding-top: .6rem; }
  summary { cursor: pointer; font-weight: 600; }
  .criteria, .technical { font-size: .875rem; }
  dt { font-weight: 600; margin-top: .5rem; } dd { margin: .2rem 0; }
  .technical { margin-top: 1rem; border-top: 1px solid var(--admin-border); padding-top: 1rem; }
  .technical-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 15rem), 1fr)); gap: .75rem 1.25rem; margin: 0; }
  .technical-facts dt { font-size: .8rem; color: var(--admin-muted); margin: 0; }
  .technical-facts dd { margin-bottom: 0; }
  .technical-overview { margin-top: .65rem; padding: .75rem 1rem; background: var(--admin-soft); border: 1px solid var(--admin-border); border-radius: 8px; }
  .technical details { padding: 0; border: 1px solid var(--admin-border); border-radius: 8px; }
  .technical summary { padding: .6rem .85rem; }
  .technical details > :is(dl, p) { margin: 0 .85rem .85rem; }
  .technical-text { max-inline-size: 68ch; line-height: 1.6; }
  footer { margin-top: 1rem; }
  @container (max-width: 40rem) {
    .indexed-report { grid-template-columns: minmax(0, 1fr); }
    nav { grid-column: 1; }
    .assessments { grid-row: 2; }
  }
</style>
