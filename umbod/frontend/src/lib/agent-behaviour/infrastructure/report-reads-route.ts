import type { Transport } from '#lib/admin/infrastructure/transport.js';
import type { ReportReadsPort } from '../api';
import { pageSchema, querySchema, reportSchema, type DiagnosticReport, type ReportPage, type ReportQuery } from '../domain/schemas';

export class ReportReadsRoute implements ReportReadsPort {
  constructor(private readonly transport: Transport, private readonly path: string) {}

  async list(query: ReportQuery, signal?: AbortSignal): Promise<ReportPage> {
    const parsed = querySchema.parse(query);
    const parameters = new URLSearchParams(Object.entries(parsed).filter((entry): boolean => entry[1] !== undefined).map(([key, value]): [string, string] => [key, String(value)]));
    return this.transport.request({ method: 'GET', path: `${this.path}?${parameters}`, outputSchema: pageSchema, signal });
  }

  get(id: string, signal?: AbortSignal): Promise<DiagnosticReport> {
    return this.transport.request({ method: 'GET', path: `${this.path}/${encodeURIComponent(id)}`, outputSchema: reportSchema, signal });
  }
}
