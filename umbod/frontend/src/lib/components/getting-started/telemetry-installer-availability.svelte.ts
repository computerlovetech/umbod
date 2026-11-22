import type { TelemetrySetupSource } from '#lib/telemetry-setup/api.js';
import { validateTelemetryEndpoint } from './installer-artifact';

export class TelemetryInstallerAvailability {
  #logsEndpoint = $state('');

  get logsEndpoint(): string { return this.#logsEndpoint; }

  async load(source: TelemetrySetupSource, signal: AbortSignal): Promise<void> {
    try {
      const setup = await source.get();
      if (signal.aborted || setup.status !== 'available') return;
      validateTelemetryEndpoint(setup.logs_endpoint);
      this.#logsEndpoint = setup.logs_endpoint;
    } catch {
      if (!signal.aborted) this.#logsEndpoint = '';
    }
  }
}
