import type { TelemetrySetupSource, TelemetrySetupApi } from './api';
import { telemetrySetupSchema, type TelemetrySetup } from './domain/schemas';

export class InMemoryTelemetrySetup implements TelemetrySetupSource, TelemetrySetupApi {
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
