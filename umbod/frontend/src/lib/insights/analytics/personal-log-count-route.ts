import type { Transport } from '#lib/admin/infrastructure/transport.js';
import { logCountQuerySchema, logCountResponseFor, type LogCountQuery, type LogCountResponse } from '#lib/admin/analytics/domain/schemas.js';
import type { LogCountSource } from '#lib/admin/analytics/port.js';

export class PersonalLogCountRoute implements LogCountSource {
  constructor(private readonly transport: Transport) {}

  query(query: LogCountQuery, signal?: AbortSignal): Promise<LogCountResponse> {
    return this.transport.request({
      method: 'POST',
      path: '/me/telemetry/log-counts',
      requestBody: { kind: 'json', value: query, schema: logCountQuerySchema },
      outputSchema: logCountResponseFor(query),
      redirect: 'error',
      signal
    });
  }
}
