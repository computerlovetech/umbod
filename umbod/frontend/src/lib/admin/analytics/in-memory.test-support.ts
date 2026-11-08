import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery, type LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

export class InMemoryLogCounts implements LogCountSource {
  readonly queries: LogCountQuery[] = [];
  response: LogCountResponse = { rows: [], has_more: false };
  failure: unknown;
  readonly signals: Array<AbortSignal | undefined> = [];
  handler: ((query: LogCountQuery) => Promise<LogCountResponse>) | undefined;

  async query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    const parsed = logCountQuerySchema.parse(query);
    this.queries.push(parsed);
    this.signals.push(signal);
    if (this.failure) throw this.failure;
    return logCountResponseSchema.parse(this.handler ? await this.handler(parsed) : this.response);
  }
}
