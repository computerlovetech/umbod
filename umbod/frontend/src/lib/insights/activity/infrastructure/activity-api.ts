import { HttpError, SchemaValidationError, type Transport } from '#lib/admin/infrastructure/transport.js';
import type { z } from 'zod';
import type { ActivityApi } from '../domain/activity-api';
import {
  activityDaysSchema,
  activityOverviewSchema,
  activitySessionKeySchema,
  activitySessionPageSchema,
  activitySessionReportSchema,
  activitySessionsQuerySchema,
  unavailableActivityOverviewSchema,
  type ActivityDays,
  type ActivityOverview,
  type ActivitySessionKey,
  type ActivitySessionPage,
  type ActivitySessionReport,
  type ActivitySessionsQuery
} from '../domain/activity-schemas';

const activityPath = '/me/activity';

function parseOutbound<T>(schema: z.ZodType<T>, value: unknown): T {
  const parsed = schema.safeParse(value);
  if (!parsed.success) throw new SchemaValidationError('outbound', parsed.error.issues);
  return parsed.data;
}

function matchesDays(days: ActivityDays): (response: { period: { days: ActivityDays } }) => boolean {
  return (response): boolean => response.period.days === days;
}

const requestedDaysIssue = { path: ['period', 'days'], message: 'Expected the requested Activity period' };

function sessionsPath(query: ActivitySessionsQuery): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  return params.size ? `${activityPath}/sessions?${params}` : `${activityPath}/sessions`;
}

class ActivityRoute implements ActivityApi {
  constructor(private readonly transport: Transport) {}

  async overview(days: ActivityDays, signal?: AbortSignal): Promise<ActivityOverview> {
    const range = parseOutbound(activityDaysSchema, days);
    const validateDays = matchesDays(range);
    try {
      return await this.transport.request({
        method: 'GET',
        path: `${activityPath}?days=${range}`,
        outputSchema: activityOverviewSchema.refine(validateDays, requestedDaysIssue),
        signal
      });
    } catch (error) {
      if (error instanceof HttpError && error.status === 503) {
        const parsed = unavailableActivityOverviewSchema.safeParse(error.body);
        if (parsed.success) {
          if (!validateDays(parsed.data)) throw new SchemaValidationError('inbound', [{ code: 'custom', ...requestedDaysIssue }]);
          return parsed.data;
        }
      }
      throw error;
    }
  }

  async sessions(query: ActivitySessionsQuery, signal?: AbortSignal): Promise<ActivitySessionPage> {
    const parsed = parseOutbound(activitySessionsQuerySchema, query);
    return this.transport.request({
      method: 'GET',
      path: sessionsPath(parsed),
      outputSchema: activitySessionPageSchema.refine(matchesDays(parsed.days ?? 7), requestedDaysIssue),
      signal
    });
  }

  async session(key: ActivitySessionKey, signal?: AbortSignal): Promise<ActivitySessionReport> {
    const { source, session_id } = parseOutbound(activitySessionKeySchema, key);
    return this.transport.request({
      method: 'GET',
      path: `${activityPath}/sessions/${source}/${encodeURIComponent(session_id)}`,
      outputSchema: activitySessionReportSchema.refine(
        ({ session }): boolean => session.key.source === source && session.key.session_id === session_id,
        { path: ['session', 'key'], message: 'Expected the requested session key' }
      ),
      signal
    });
  }
}

export function createActivityApi(transport: Transport): ActivityApi {
  return new ActivityRoute(transport);
}
