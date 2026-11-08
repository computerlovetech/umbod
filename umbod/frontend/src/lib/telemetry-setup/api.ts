import type { TelemetrySetup } from './domain/schemas';

export interface TelemetrySetupSource {
  get(): Promise<TelemetrySetup>;
}

export interface TelemetrySetupApi {
  readonly setup: TelemetrySetupSource;
}
