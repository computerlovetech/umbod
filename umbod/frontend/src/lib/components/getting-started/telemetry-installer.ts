import type { InstallationHarness, InstallationPlatform } from './plugin-installation-state.svelte';

export interface TelemetryInstaller {
  prepare(platform: InstallationPlatform, harness: InstallationHarness, signal?: AbortSignal): Promise<Blob>;
}
