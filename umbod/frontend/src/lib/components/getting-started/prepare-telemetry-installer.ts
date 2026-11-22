import type { PersonalAccessTokensPort } from '#lib/personal-access-tokens/api.js';
import type { TelemetrySetupSource } from '#lib/telemetry-setup/api.js';
import { normalizeInstallationUrl } from './installation-url';
import { privateTelemetryInstaller, supportsTelemetry, validateTelemetryEndpoint, type InstallerArtifactSource } from './installer-artifact';
import type { InstallationHarness, InstallationPlatform } from './plugin-installation-state.svelte';
import type { TelemetryInstaller } from './telemetry-installer';

const tokenLifetimeMilliseconds = 30 * 86_400_000;

export class PrepareTelemetryInstaller implements TelemetryInstaller {
  constructor(
    private readonly installerBaseUrl: () => string,
    private readonly setup: TelemetrySetupSource,
    private readonly tokens: PersonalAccessTokensPort,
    private readonly artifacts: InstallerArtifactSource,
    private readonly now: () => number
  ) {}

  async prepare(platform: InstallationPlatform, harness: InstallationHarness, signal?: AbortSignal): Promise<Blob> {
    signal?.throwIfAborted();
    if (harness !== 'claude-code') throw new Error('Automatic telemetry setup is unavailable for this harness.');
    const extension = platform === 'windows' ? 'ps1' : 'sh';
    const base = normalizeInstallationUrl(this.installerBaseUrl());
    const setup = await this.setup.get();
    if (setup.status !== 'available') throw new Error('Telemetry is unavailable.');
    const endpoint = validateTelemetryEndpoint(setup.logs_endpoint);
    const artifact = await this.artifacts.read(`${base}/${harness}/install.${extension}`);
    if (!supportsTelemetry(artifact, platform)) throw new Error('The installer does not support automatic telemetry setup.');
    signal?.throwIfAborted();
    const created = await this.tokens.create({
      name: 'Claude Code installer telemetry',
      expires_at: new Date(this.now() + tokenLifetimeMilliseconds).toISOString(),
      permissions: { telemetry: 'write' }
    });
    try {
      signal?.throwIfAborted();
      return privateTelemetryInstaller(artifact, platform, endpoint, created.token);
    } catch (error) {
      await this.tokens.revoke(created.metadata.token_id).catch((): void => {});
      throw error;
    }
  }
}
