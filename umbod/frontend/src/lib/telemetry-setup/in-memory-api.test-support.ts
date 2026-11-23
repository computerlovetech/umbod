import type { TelemetrySetupSource, TelemetrySetupApi, TelemetryInstallClaims } from './api';
import { telemetryInstallClaimRequestSchema, telemetryInstallClaimSchema, telemetrySetupSchema, type TelemetryInstallClaim, type TelemetryInstallClaimRequest, type TelemetrySetup } from './domain/schemas';

export class InMemoryTelemetryInstallClaims implements TelemetryInstallClaims {
  requests: { request: TelemetryInstallClaimRequest; signal: AbortSignal }[] = [];
  code: string = 'A'.repeat(43);
  beforeCreate: () => Promise<void> = async (): Promise<void> => {};

  async create(request: TelemetryInstallClaimRequest, signal: AbortSignal): Promise<TelemetryInstallClaim> {
    this.requests.push({ request: telemetryInstallClaimRequestSchema.parse(request), signal });
    await this.beforeCreate();
    return telemetryInstallClaimSchema.parse({ code: this.code });
  }
}

export class InMemoryTelemetrySetup implements TelemetrySetupSource, TelemetrySetupApi {
  readonly installClaims = new InMemoryTelemetryInstallClaims();
  readonly setup: TelemetrySetupSource = this;
  value: TelemetrySetup = { status: 'available', logs_endpoint: 'https://collector.example/prefix/v1/logs' };
  failure: Error | undefined;
  beforeGet: () => Promise<void> = async (): Promise<void> => {};
  calls = 0;

  async get(): Promise<TelemetrySetup> {
    this.calls += 1;
    await this.beforeGet();
    if (this.failure) throw this.failure;
    return telemetrySetupSchema.parse(this.value);
  }
}
