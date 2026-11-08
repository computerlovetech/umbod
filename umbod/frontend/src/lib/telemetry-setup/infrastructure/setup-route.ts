import type { Transport } from '$lib/admin/infrastructure/transport';
import type { TelemetrySetupSource } from '../api';
import { telemetrySetupSchema, type TelemetrySetup } from '../domain/schemas';

export class SetupRoute implements TelemetrySetupSource {
  constructor(private readonly transport: Transport) {}

  get(): Promise<TelemetrySetup> {
    return this.transport.request({ method: 'GET', path: '/me/telemetry/setup', outputSchema: telemetrySetupSchema });
  }
}
