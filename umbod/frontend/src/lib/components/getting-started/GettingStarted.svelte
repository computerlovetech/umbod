<script lang="ts">
  import { onMount } from 'svelte';
  import SubpageContainer from '#lib/components/shared/workspace/SubpageContainer.svelte';
  import { browserPersonalAccessTokensApi } from '#lib/personal-access-tokens/infrastructure/api.js';
  import { browserTelemetrySetupApi } from '#lib/telemetry-setup/infrastructure/api.js';
  import McpSetupGuide from './McpSetupGuide.svelte';
  import { BrowserInstallerArtifactSource } from './installer-artifact';
  import { PrepareTelemetryInstaller } from './prepare-telemetry-installer';
  import { TelemetryInstallerAvailability } from './telemetry-installer-availability.svelte';

  let { installerBaseUrl }: { installerBaseUrl: string } = $props();
  const setup = browserTelemetrySetupApi().setup;
  const availability = new TelemetryInstallerAvailability();
  const telemetryInstaller = new PrepareTelemetryInstaller(
    (): string => installerBaseUrl,
    setup,
    browserPersonalAccessTokensApi().tokens,
    new BrowserInstallerArtifactSource(globalThis.fetch),
    Date.now
  );

  onMount((): (() => void) => {
    const controller = new AbortController();
    void availability.load(setup, controller.signal);
    return (): void => controller.abort();
  });
</script>

<svelte:head><title>Getting started · Umbod</title></svelte:head>

<SubpageContainer title="Getting started" lede="Install the Umbod plugin for Codex or Claude Code so your coding agent can use the tools available to you in Umbod.">
  <McpSetupGuide {installerBaseUrl} telemetryInstaller={availability.available ? telemetryInstaller : undefined} />
</SubpageContainer>
