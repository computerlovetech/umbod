<script lang="ts">
  import type { PersonalReportsState } from '#lib/agent-behaviour/state/personal-reports-state.svelte.js';
  import ReportsView from '#lib/components/shared/agent-behaviour/ReportsView.svelte';

  let { state }: { state: PersonalReportsState } = $props();
</script>

<header class="insight-heading">
  <h2>Agent behaviour</h2>
</header>
{#if state.allowed}
  <ReportsView state={state.reports} />
{:else}
  <p role="alert">Your entries are no longer available. Reload or sign in again.</p>
{/if}
