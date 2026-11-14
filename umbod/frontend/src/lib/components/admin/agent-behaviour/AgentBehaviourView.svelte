<script lang="ts">
  import type { AgentBehaviourPageState } from '$lib/agent-behaviour/state/page-state.svelte';
  import ReportsView from './ReportsView.svelte';
  let { state }: { state: AgentBehaviourPageState } = $props();
</script>

<header class="insight-heading">
  <h2>Agent behaviour</h2>
</header>
{#if state.allowed}
  <ReportsView state={state.reports} />
{:else}
  <p role="alert">Administration access is no longer available. Reload or sign in again.</p>
{/if}
