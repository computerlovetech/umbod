<script lang="ts">
  import InsightsLayout from './InsightsLayout.svelte';
  import BehaviourPage from '../../../../routes/admin/insights/agent-behaviour/+page.svelte';
  import ConfigurationPage from '../../../../routes/admin/insights/agent-behaviour/configuration/+page.svelte';
  import LogsPage from '../../../../routes/admin/insights/logs/+page.svelte';
  import type { InsightsState } from './insights-state.svelte';
  import type { InsightsHarnessState } from './insights.test-support.svelte';

  let { controls, createState }: { controls: InsightsHarnessState; createState: () => InsightsState } = $props();
</script>

<svelte:document onclick={controls.navigate} />
<InsightsLayout accountIdentity={controls.identity} pathname={controls.pathname} {createState}>
  {#if controls.pathname.endsWith('/configuration')}
    <ConfigurationPage />
  {:else if controls.pathname.endsWith('/logs')}
    <LogsPage />
  {:else}
    <BehaviourPage />
  {/if}
</InsightsLayout>
