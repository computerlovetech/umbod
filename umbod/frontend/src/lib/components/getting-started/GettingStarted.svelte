<script lang="ts">
  import SubpageContainer from '$lib/components/shared/workspace/SubpageContainer.svelte';
  import SubpageNavigation, { type SubpageLink } from '$lib/components/shared/workspace/SubpageNavigation.svelte';
  import McpSetupGuide from './McpSetupGuide.svelte';
  import TelemetrySetup from './TelemetrySetup.svelte';

  let {
    installerBaseUrl,
    activePage = 'connect'
  }: {
    installerBaseUrl: string;
    activePage?: 'connect' | 'telemetry';
  } = $props();

  const subpages: readonly SubpageLink[] = [
    { id: 'connect', label: 'Connect your harness', href: '/getting-started' },
    { id: 'telemetry', label: 'Set up telemetry', href: '/getting-started/telemetry' }
  ];

</script>

<svelte:head><title>Getting started · Umbod</title></svelte:head>

<SubpageContainer title="Getting started" lede="">
  {#snippet navigation()}
    <SubpageNavigation links={subpages} activeId={activePage} label="Setup sections" />
  {/snippet}
  {#if activePage === 'connect'}
    <McpSetupGuide {installerBaseUrl} />
  {:else}
    <TelemetrySetup />
  {/if}
</SubpageContainer>

