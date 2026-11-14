import type { Configuration, PublishConfiguration, ReportQuery, ReportPage, DiagnosticReport } from './domain/schemas';

export interface ConfigurationPort {
  defaults(signal?: AbortSignal): Promise<Configuration>;
  get(signal?: AbortSignal): Promise<Configuration>;
  publish(command: PublishConfiguration, signal?: AbortSignal): Promise<Configuration>;
}
export interface ReportsPort {
  list(query: ReportQuery, signal?: AbortSignal): Promise<ReportPage>;
  get(id: string, signal?: AbortSignal): Promise<DiagnosticReport>;
  remove(id: string, signal?: AbortSignal): Promise<void>;
}
export interface AgentBehaviourPort {
  configuration: ConfigurationPort;
  reports: ReportsPort;
}
