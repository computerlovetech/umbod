import type { Transport } from '../infrastructure/transport';
import { logCountQuerySchema, logCountResponseSchema, type LogCountQuery, type LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

export class AnalyticsRoute implements LogCountSource {
  constructor(private readonly transport: Transport) {}

  query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    return this.transport.request({
      method: 'POST', path: '/admin/telemetry/log-counts',
      requestBody: { kind: 'json', value: query, schema: logCountQuerySchema },
      outputSchema: logCountResponseSchema.refine((response) =>
        response.rows.length <= query.max_groups && response.rows.every((row) =>
          row.groups.length === query.group_by.length &&
          row.groups.every((group, index) => group.dimension === query.group_by[index]) &&
          row.bucket.kind === (query.bucketing.kind === 'fixed' ? 'bucket' : 'none')
        ), 'Aggregate results must match the requested grouping, buckets and group limit'
      ), signal
    });
  }
}
