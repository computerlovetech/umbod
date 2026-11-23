import type { TelemetryInstallClaim, TelemetryInstallClaimRequest, TelemetrySetup } from './domain/schemas';

export interface TelemetrySetupSource {
  get(): Promise<TelemetrySetup>;
}

export interface TelemetryInstallClaims {
  create(request: TelemetryInstallClaimRequest, signal: AbortSignal): Promise<TelemetryInstallClaim>;
}

export interface TelemetrySetupApi {
  readonly setup: TelemetrySetupSource;
  readonly installClaims: TelemetryInstallClaims;
}
