import type { TelemetrySetupSource } from '#lib/telemetry-setup/api.js';
import { validateTelemetryEndpoint } from './installer-artifact';

export class TelemetryInstallerAvailability {
  available = $state(false);

  async load(source: TelemetrySetupSource, signal: AbortSignal): Promise<void> {
    try {
      const setup = await source.get();
      if (signal.aborted || setup.status !== 'available') return;
      validateTelemetryEndpoint(setup.logs_endpoint);
      this.available = true;
    } catch {
      if (!signal.aborted) this.available = false;
    }
  }
}
