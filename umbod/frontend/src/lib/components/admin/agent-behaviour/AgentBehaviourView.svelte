<script lang="ts">
  import type { AgentBehaviourPageState } from '#lib/agent-behaviour/state/page-state.svelte.js';
  import ButtonLink from '#lib/components/admin/shared/ButtonLink.svelte';
  import { agentBehaviourFindingsHref, agentDiagnosticsHref, agentDiagnosticsReportingHref } from '#lib/workspace/navigation.js';
  import Button from '#lib/components/admin/shared/Button.svelte';
  import DateTimeView from '#lib/components/shared/DateTimeView.svelte';
  import ModalShell from '#lib/components/shared/ModalShell.svelte';
  import ReportsView from '#lib/components/shared/agent-behaviour/ReportsView.svelte';
  import ReportDetailView from '#lib/components/shared/agent-behaviour/ReportDetailView.svelte';
  let { state, reportId = null, onDeleted }: { state: AgentBehaviourPageState; reportId?: string | null; onDeleted?: () => void | Promise<void> } = $props();
  async function removeReport(): Promise<void> {
    if (await state.reports.remove()) await onDeleted?.();
  }
</script>

{#if state.allowed}
  {#if reportId === null}
    <header class="insight-heading findings-heading">
      <h2>Agent behaviour</h2>
      <a class="admin-back-link" href={agentDiagnosticsReportingHref}>Collection settings</a>
    </header>
    {#if state.configuration.collectionStatus === 'unconfigured'}
      <div class="insight-results collection-notice">
        <strong>Collection isn’t configured</strong>
        <ButtonLink variant="secondary" href={agentDiagnosticsHref}>Set up collection</ButtonLink>
      </div>
    {:else if state.configuration.collectionStatus === 'off'}
      <div class="insight-results collection-notice">
        <div><strong>Collection is off</strong><p class="insight-caption">Existing entries remain available.</p></div>
        <ButtonLink variant="secondary" href={agentDiagnosticsReportingHref}>Review collection settings</ButtonLink>
      </div>
    {/if}
    <ReportsView state={state.reports} listHref={agentBehaviourFindingsHref} />
  {:else}
    {#key reportId}
      <ReportDetailView state={state.reports} {reportId} listHref={agentBehaviourFindingsHref}>
        {#snippet actions()}
          <Button variant="danger" disabled={state.reports.detailBusy} onclick={state.reports.confirmDelete}>Delete entry</Button>
        {/snippet}
      </ReportDetailView>
    {/key}
  {/if}
  {#if state.reports.deleteConfirmation && state.reports.detail}
    <ModalShell title="Delete this entry?" titleId="delete-report-title" close={state.reports.cancelDelete} closeDisabled={state.reports.detailBusy} role="alertdialog">
      <p>{state.reports.detail.report_id} · <DateTimeView value={state.reports.detail.received_at} /></p>
      <p>Evidence and instructions are deleted immediately. This cannot be undone. An opaque retry receipt remains until 60 days after reporting.</p>
      {#if state.reports.message}<p role="alert">{state.reports.message}</p>{/if}
      <div class="actions"><Button variant="secondary" data-dialog-cancel disabled={state.reports.detailBusy} onclick={state.reports.cancelDelete}>Cancel</Button><Button variant="danger" disabled={state.reports.detailBusy} onclick={removeReport}>Delete permanently</Button></div>
    </ModalShell>
  {/if}
{:else}
  <p role="alert">Administration access is no longer available. Reload or sign in again.</p>
{/if}

<style>
  .actions { display: flex; align-items: center; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }
  .findings-heading, .collection-notice { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem 1.5rem; }
  .findings-heading a { margin-bottom: 0; }
  .collection-notice { margin-bottom: 1rem; }
  .collection-notice p { margin-bottom: 0; }
</style>
