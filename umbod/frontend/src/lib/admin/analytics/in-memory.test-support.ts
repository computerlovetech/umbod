import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery, type LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

export class InMemoryLogCounts implements LogCountSource {
  readonly queries: LogCountQuery[] = [];
  response: LogCountResponse = { rows: [] };
  failure: unknown;
  handler: ((query: LogCountQuery) => Promise<LogCountResponse>) | undefined;

  async query(query: LogCountQuery): Promise<LogCountResponse> {
    const parsed = logCountQuerySchema.parse(query);
    this.queries.push(parsed);
    if (this.failure) throw this.failure;
    return logCountResponseSchema.parse(this.handler ? await this.handler(parsed) : this.response);
  }
}
