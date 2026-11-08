import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery, type LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

export function isClassificationQuery(query: LogCountQuery): boolean {
  return query.group_by.length === 1 && query.group_by[0] === 'activity_kind' && query.bucketing.kind === 'none' && query.pagination.limit === 1000;
}

export class InMemoryLogCounts implements LogCountSource {
  readonly queries: LogCountQuery[] = [];
  response: LogCountResponse = { rows: [], has_more: false };
  classificationResponse: LogCountResponse = { rows: [], has_more: false };

  get reportQueries(): LogCountQuery[] { return this.queries.filter((query) => !isClassificationQuery(query)); }
  get coverageQueries(): LogCountQuery[] { return this.queries.filter(isClassificationQuery); }
  failure: unknown;
  readonly signals: Array<AbortSignal | undefined> = [];
  handler: ((query: LogCountQuery) => Promise<LogCountResponse>) | undefined;

  async query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    const parsed = logCountQuerySchema.parse(query);
    this.queries.push(parsed);
    this.signals.push(signal);
    if (this.failure) throw this.failure;
    return logCountResponseSchema.parse(this.handler ? await this.handler(parsed) : isClassificationQuery(parsed) ? this.classificationResponse : this.response);
  }
}
