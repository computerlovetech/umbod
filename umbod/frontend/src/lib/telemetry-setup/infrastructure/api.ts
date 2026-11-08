import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { TelemetrySetupApi } from '../api';
import { SetupRoute } from './setup-route';

export class HttpTelemetrySetupApi implements TelemetrySetupApi {
  readonly setup: SetupRoute;

  constructor(transport: Transport) {
    this.setup = new SetupRoute(transport);
  }
}

export function browserTelemetrySetupApi(request: typeof fetch = globalThis.fetch): TelemetrySetupApi {
  return new HttpTelemetrySetupApi(browserTransport({ fetch: request }));
}
