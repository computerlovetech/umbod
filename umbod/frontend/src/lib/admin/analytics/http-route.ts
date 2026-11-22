import type { Transport } from '../infrastructure/transport';
import { logCountQuerySchema, logCountResponseFor, type LogCountQuery, type LogCountResponse } from './domain/schemas';
import type { LogCountSource } from './port';

export class AnalyticsRoute implements LogCountSource {
  constructor(private readonly transport: Transport) {}

  query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    return this.transport.request({
      method: 'POST', path: '/admin/telemetry/log-counts',
      requestBody: { kind: 'json', value: query, schema: logCountQuerySchema },
      outputSchema: logCountResponseFor(query), signal
    });
  }
}
