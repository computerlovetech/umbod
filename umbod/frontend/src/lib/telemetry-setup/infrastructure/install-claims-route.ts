import type { Transport } from '#lib/admin/infrastructure/transport.js';
import type { TelemetryInstallClaims } from '../api';
import { telemetryInstallClaimRequestSchema, telemetryInstallClaimSchema, type TelemetryInstallClaim, type TelemetryInstallClaimRequest } from '../domain/schemas';

export class InstallClaimsRoute implements TelemetryInstallClaims {
  constructor(private readonly transport: Transport) {}

  create(request: TelemetryInstallClaimRequest, signal: AbortSignal): Promise<TelemetryInstallClaim> {
    return this.transport.request({
      method: 'POST',
      path: '/me/telemetry/install-claims',
      requestBody: { kind: 'json', value: request, schema: telemetryInstallClaimRequestSchema },
      outputSchema: telemetryInstallClaimSchema,
      redirect: 'error',
      signal
    });
  }
}
