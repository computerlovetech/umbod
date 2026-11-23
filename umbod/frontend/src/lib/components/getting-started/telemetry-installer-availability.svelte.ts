import type { TelemetrySetupSource } from '#lib/telemetry-setup/api.js';

export class TelemetryInstallerAvailability {
  #available = $state(false);

  get available(): boolean { return this.#available; }

  async load(source: TelemetrySetupSource, signal: AbortSignal): Promise<void> {
    try {
      const setup = await source.get();
      if (!signal.aborted) this.#available = setup.status === 'available';
    } catch {
      if (!signal.aborted) this.#available = false;
    }
  }
}
