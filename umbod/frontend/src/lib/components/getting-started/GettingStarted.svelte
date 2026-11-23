<script lang="ts">
  import { onMount } from 'svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { browserTelemetrySetupApi } from '#lib/telemetry-setup/infrastructure/api.js';
  import McpSetupGuide from './McpSetupGuide.svelte';
  import { TelemetryInstallerAvailability } from './telemetry-installer-availability.svelte';

  let { installerBaseUrl }: { installerBaseUrl: string } = $props();
  const telemetry = browserTelemetrySetupApi();
  const availability = new TelemetryInstallerAvailability();

  onMount((): (() => void) => {
    const controller = new AbortController();
    void availability.load(telemetry.setup, controller.signal);
    return (): void => controller.abort();
  });
</script>

<svelte:head><title>Getting started · Umbod</title></svelte:head>

<SubpageContainer title="Getting started" lede="Install the Umbod plugin for Codex or Claude Code so your coding agent can use the tools available to you in Umbod.">
  <McpSetupGuide {installerBaseUrl} installClaims={availability.available ? telemetry.installClaims : undefined} />
</SubpageContainer>
