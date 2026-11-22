import { browserTransport, type Transport } from '#lib/admin/infrastructure/transport.js';
import type { AgentBehaviourPort, ConfigurationPort, ReportsPort } from '../api';
import { configurationSchema, publishSchema, type Configuration, type PublishConfiguration } from '../domain/schemas';
import { ReportReadsRoute } from './report-reads-route';
const base = '/admin/agent-behaviour';
export class ConfigurationRoute implements ConfigurationPort {
  constructor(private readonly transport: Transport) {}
  defaults(signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'GET', path: `${base}/defaults`, outputSchema: configurationSchema, signal }); }
  get(signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'GET', path: `${base}/configuration`, outputSchema: configurationSchema, signal }); }
  publish(command: PublishConfiguration, signal?: AbortSignal): Promise<Configuration> { return this.transport.request({ method: 'PUT', path: `${base}/configuration`, body: command, inputSchema: publishSchema, outputSchema: configurationSchema, signal }); }
}
export class ReportsRoute extends ReportReadsRoute implements ReportsPort {
  constructor(private readonly adminTransport: Transport) { super(adminTransport, `${base}/reports`); }
  remove(id: string, signal?: AbortSignal): Promise<void> { return this.adminTransport.request({ method: 'DELETE', path: `${base}/reports/${encodeURIComponent(id)}`, signal }); }
}
export class AgentBehaviourApi implements AgentBehaviourPort {
  readonly configuration: ConfigurationRoute;
  readonly reports: ReportsRoute;
  constructor(transport: Transport) { this.configuration = new ConfigurationRoute(transport); this.reports = new ReportsRoute(transport); }
}
export function agentBehaviourApi(fetch?: typeof globalThis.fetch): AgentBehaviourPort { return new AgentBehaviourApi(browserTransport({ fetch })); }
