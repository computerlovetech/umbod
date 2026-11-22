<script lang="ts">
  import type { AgentBehaviourPageState } from '#lib/agent-behaviour/state/page-state.svelte.js';
  import ButtonLink from '#lib/components/admin/shared/ButtonLink.svelte';
  import { agentDiagnosticsHref } from '#lib/workspace/navigation.js';
  import ReportsView from './ReportsView.svelte';
  let { state }: { state: AgentBehaviourPageState } = $props();
</script>

<header class="insight-heading findings-heading">
  <h2>Agent behaviour</h2>
  {#if state.allowed}<a class="admin-back-link" href={agentDiagnosticsHref}>Collection settings</a>{/if}
</header>
{#if state.allowed}
  {#if state.configuration.collectionStatus === 'unconfigured'}
    <div class="insight-results collection-notice">
      <strong>Collection isn’t configured</strong>
      <ButtonLink variant="secondary" href={agentDiagnosticsHref}>Set up collection</ButtonLink>
    </div>
  {:else if state.configuration.collectionStatus === 'off'}
    <div class="insight-results collection-notice">
      <div><strong>Collection is off</strong><p class="insight-caption">Existing entries remain available.</p></div>
      <ButtonLink variant="secondary" href={agentDiagnosticsHref}>Review collection settings</ButtonLink>
    </div>
  {/if}
  <ReportsView state={state.reports} />
{:else}
  <p role="alert">Administration access is no longer available. Reload or sign in again.</p>
{/if}

<style>
  .findings-heading, .collection-notice { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .75rem 1.5rem; }
  .findings-heading a { margin-bottom: 0; }
  .collection-notice { margin-bottom: 1rem; }
  .collection-notice p { margin-bottom: 0; }
</style>
