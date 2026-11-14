import type { Dimension, LogCountQuery } from './domain/schemas';

export type ReportId = 'tools' | 'files' | 'skills' | 'logs' | 'custom';

export const reportOptions: { value: ReportId; label: string }[] = [
  { value: 'tools', label: 'Tool calls' },
  { value: 'files', label: 'File activity' },
  { value: 'skills', label: 'Skill activity' },
  { value: 'logs', label: 'Stored logs' },
  { value: 'custom', label: 'Custom log query' }
];
export type ActivityReportId = Exclude<ReportId, 'custom'>;

interface ReportDefinition {
  readonly label: string;
  readonly countLabel: string;
  readonly activities: readonly string[];
  readonly groups: readonly Dimension[];
}

export const reports: Record<ActivityReportId, ReportDefinition> = {
  logs: {
    label: 'Stored logs',
    countLabel: 'Log records',
    activities: [],
    groups: ['activity_kind', 'source', 'event_name', 'tool_name', 'session_id']
  },
  tools: {
    label: 'Tool calls',
    countLabel: 'Reported tool calls',
    activities: ['tool_call', 'file_read', 'file_edit'],
    groups: ['source', 'session_id', 'outcome']
  },
  files: {
    label: 'File activity',
    countLabel: 'Read/edit-tool calls',
    activities: ['file_read', 'file_edit'],
    groups: ['source', 'session_id', 'activity_kind']
  },
  skills: {
    label: 'Skill activity',
    countLabel: 'Skill activations',
    activities: ['skill_activation'],
    groups: ['source', 'session_id']
  }
};

export function resolveReport(report: ActivityReportId, timeRange: LogCountQuery['time_range']): LogCountQuery {
  const definition = reports[report];
  return {
    time_range: timeRange,
    filters: definition.activities.length ? [{ dimension: 'activity_kind', values: [...definition.activities] }] : [],
    group_by: [...definition.groups],
    bucketing: { kind: 'none' },
    pagination: { limit: 100, offset: 0 }
  };
}

export function reportValue(dimension: Dimension, value: string): string {
  if (dimension === 'outcome') return ({ success: 'Successful', failure: 'Failed', unknown: 'Unknown outcome' })[value] ?? value;
  if (dimension === 'activity_kind' && value === '') return 'Unclassified';
  if (dimension === 'activity_kind') return ({ tool_call: 'Tool calls', skill_activation: 'Skill activations', file_read: 'Read-tool calls', file_edit: 'Edit-tool calls' })[value] ?? value;
  return value === '' ? 'Not reported' : value;
}
