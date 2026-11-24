<script lang="ts">
  import type { PersonalReportsState } from '#lib/agent-behaviour/state/personal-reports-state.svelte.js';
  import ReportsView from '#lib/components/shared/agent-behaviour/ReportsView.svelte';

  import ReportDetailView from '#lib/components/shared/agent-behaviour/ReportDetailView.svelte';
  import { personalInsightsHref } from '#lib/workspace/navigation.js';

  let { state, reportId = null }: { state: PersonalReportsState; reportId?: string | null } = $props();
</script>

{#if state.allowed}
  {#if reportId !== null}
    {#key reportId}<ReportDetailView state={state.reports} {reportId} listHref={personalInsightsHref} />{/key}
  {:else}
    <header class="insight-heading"><h2>Agent behaviour</h2></header>
    <ReportsView state={state.reports} listHref={personalInsightsHref} />
  {/if}
{:else}
  <p role="alert">Your entries are no longer available. Reload or sign in again.</p>
{/if}
