import { browserTransport, type Transport } from '#lib/admin/infrastructure/transport.js';
import type { TelemetrySetupApi } from '../api';
import { InstallClaimsRoute } from './install-claims-route';
import { SetupRoute } from './setup-route';

export class HttpTelemetrySetupApi implements TelemetrySetupApi {
  readonly setup: SetupRoute;
  readonly installClaims: InstallClaimsRoute;

  constructor(transport: Transport) {
    this.setup = new SetupRoute(transport);
    this.installClaims = new InstallClaimsRoute(transport);
  }
}

export function browserTelemetrySetupApi(request: typeof fetch = globalThis.fetch): TelemetrySetupApi {
  return new HttpTelemetrySetupApi(browserTransport({ fetch: request }));
}
