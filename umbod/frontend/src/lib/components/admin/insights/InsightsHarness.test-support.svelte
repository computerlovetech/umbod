<script lang="ts">
  import InsightsLayout from './InsightsLayout.svelte';
  import BehaviourPage from '../../../../routes/admin/(agent-insights)/insights/agent-behaviour/+page.svelte';
  import ConfigurationPage from '../../../../routes/admin/(agent-insights)/agent-diagnostics/+page.svelte';
  import LogsPage from '../../../../routes/admin/(agent-insights)/insights/logs/+page.svelte';
  import type { InsightsState } from './insights-state.svelte';
  import type { InsightsHarnessState } from './insights.test-support.svelte';

  let { controls, createState }: { controls: InsightsHarnessState; createState: () => InsightsState } = $props();
</script>

<svelte:document onclick={controls.navigate} />
<InsightsLayout accountIdentity={controls.identity} pathname={controls.pathname} {createState}>
  {#if controls.pathname === '/admin/agent-diagnostics'}
    <ConfigurationPage />
  {:else if controls.pathname.endsWith('/logs')}
    <LogsPage />
  {:else}
    <BehaviourPage />
  {/if}
</InsightsLayout>
