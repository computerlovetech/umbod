import { browserTransport, type Transport } from '$lib/admin/infrastructure/transport';
import type { AgentBehaviourPort, ConfigurationPort, ReportsPort } from '../api';
import { configurationSchema, publishSchema, querySchema, pageSchema, reportSchema, type Configuration, type PublishConfiguration, type ReportQuery, type ReportPage, type DiagnosticReport } from '../domain/schemas';
const base = '/admin/agent-behaviour';
export class ConfigurationRoute implements ConfigurationPort {
  constructor(private readonly transport: Transport) {}
  defaults(signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'GET', path: `${base}/defaults`, outputSchema: configurationSchema, signal }); }
  get(signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'GET', path: `${base}/configuration`, outputSchema: configurationSchema, signal }); }
  publish(command: PublishConfiguration, signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'PUT', path: `${base}/configuration`, body: command, inputSchema: publishSchema, outputSchema: configurationSchema, signal }); }
}
export class ReportsRoute implements ReportsPort {
  constructor(private readonly transport: Transport) {}
  list(query: ReportQuery, signal?: AbortSignal): Promise<ReportPage> {
    const parsed = querySchema.parse(query);
    const parameters = new URLSearchParams(Object.entries(parsed).filter((entry): boolean => entry[1] !== undefined).map(([key, value]): [string, string] => [key, String(value)]));
    return this.transport.request({ method: 'GET', path: `${base}/reports?${parameters}`, outputSchema: pageSchema, signal });
  }
  get(id: string, signal?: AbortSignal): Promise<DiagnosticReport> { return this.transport.request({ method: 'GET', path: `${base}/reports/${encodeURIComponent(id)}`, outputSchema: reportSchema, signal }); }
  remove(id: string, signal?: AbortSignal): Promise<void> { return this.transport.request({ method: 'DELETE', path: `${base}/reports/${encodeURIComponent(id)}`, signal }); }
}
export class AgentBehaviourApi implements AgentBehaviourPort {
  readonly configuration: ConfigurationRoute;
  readonly reports: ReportsRoute;
  constructor(transport: Transport) { this.configuration = new ConfigurationRoute(transport); this.reports = new ReportsRoute(transport); }
}
export function agentBehaviourApi(fetch?: typeof globalThis.fetch): AgentBehaviourPort { return new AgentBehaviourApi(browserTransport({ fetch })); }
