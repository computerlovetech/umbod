import { HttpError } from '#lib/admin/infrastructure/transport.js';
import type { AgentBehaviourPort, ConfigurationPort, ReportsPort } from './api';
import { publishSchema, type Configuration, type PublishConfiguration, type ReportPage, type DiagnosticReport, type ReportQuery } from './domain/schemas';
export class InMemoryAgentBehaviourApi implements AgentBehaviourPort {
  current: Configuration = { revision: 0, reporting_enabled: false, patterns: [], playbooks: [] };
  defaults: Configuration = { revision: 1, reporting_enabled: false, patterns: [], playbooks: [] };
  rows: DiagnosticReport[] = [];
  readonly configuration: ConfigurationPort = {
    defaults: async (): Promise<Configuration> => structuredClone(this.defaults),
    get: async (): Promise<Configuration> => structuredClone(this.current),
    publish: async (command: PublishConfiguration): Promise<Configuration> => {
      const value = publishSchema.parse(command);
      if (value.expected_revision !== this.current.revision) throw new HttpError(409, 'Conflict', { detail: { code: 'revision_conflict', current: this.current } });
      const invalidReference = value.playbooks.some((setting): boolean => setting.pattern_ids.some((id): boolean => !value.patterns.some((pattern): boolean => pattern.id === id) && !this.current.playbooks.some((prior): boolean => prior.id === setting.id && prior.pattern_ids.includes(id))));
      if (invalidReference) throw new HttpError(422, 'Invalid configured membership', null);
      this.current = { revision: this.current.revision + 1, reporting_enabled: value.reporting_enabled, patterns: value.patterns, playbooks: value.playbooks };
      return structuredClone(this.current);
    }
  };
  readonly reports: ReportsPort = {
    list: async (query: ReportQuery): Promise<ReportPage> => {
      const rows = this.rows.filter((row): boolean => (!query.playbook_id || row.submission.playbook_id === query.playbook_id) && row.submission.assessments.some((assessment): boolean => (!query.pattern_id || assessment.pattern_id === query.pattern_id) && (!query.status || assessment.status === query.status)));
      return { total: rows.length, items: rows.slice(query.offset, query.offset + query.limit).map((row): ReportPage['items'][number] => ({ report_id: row.report_id, received_at: row.received_at, expires_at: row.expires_at, caller: row.caller, playbook_id: row.submission.playbook_id, configuration_revision: row.submission.configuration_revision, trigger: row.submission.trigger, observed_pattern_ids: row.submission.assessments.filter((item): boolean => item.status === 'observed').map((item): string => item.pattern_id) })) };
    },
    get: async (id: string): Promise<DiagnosticReport> => { const row = this.rows.find((item): boolean => item.report_id === id); if (!row) throw new HttpError(404, 'Not found', null); return structuredClone(row); },
    remove: async (id: string): Promise<void> => { this.rows = this.rows.filter((item): boolean => item.report_id !== id); }
  };
}
export function storedReport(): DiagnosticReport {
  const patterns: DiagnosticReport['instructions']['patterns'] = [
    { id: 'fallback', name: 'Fallback observed', description: 'Look for fallback', assessment_prompt: 'Assess fallback', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true },
    { id: 'missing-context', name: 'Missing context', description: 'Look for missing context', assessment_prompt: 'Assess context', inclusion_criteria: '', exclusion_criteria: '', categories: [], polarity: 'neutral', enabled: true }
  ];
  return {
    report_id: '00000000-0000-4000-8000-000000000001',
    received_at: '2026-06-01T00:00:00Z',
    expires_at: '2026-07-01T00:00:00Z',
    caller: { authentication: 'upstream_verified', subject: { issuer: { value: 'issuer' }, subject: 'owner' } },
    submission: {
      idempotency_key: '00000000-0000-4000-8000-000000000002', configuration_revision: 1, playbook_id: 'review',
      trigger: 'user_requested',
      assessments: [
        { pattern_id: 'fallback', status: 'observed', summary: 'Fallback was used', evidence: ['The agent retried with a different tool'] },
        { pattern_id: 'missing-context', status: 'not_observed', summary: '', evidence: [] }
      ]
    },
    instructions: {
      configuration_revision: 1,
      playbook: { id: 'review', name: 'Historical review', collection_instructions: 'Collect facts', pattern_ids: ['fallback', 'missing-context'], enabled: true },
      patterns, reporting_guidance: 'Report facts only', resource_uri: 'umbod://agent-behaviour/playbooks/review'
    }
  };
}

export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void } {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((accept): void => { resolve = accept; });
  return { promise, resolve };
}
