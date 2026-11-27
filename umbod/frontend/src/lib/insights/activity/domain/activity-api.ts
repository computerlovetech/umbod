import type {
  ActivityDays,
  ActivityOverview,
  ActivitySessionKey,
  ActivitySessionPage,
  ActivitySessionReport,
  ActivitySessionsQuery
} from './activity-schemas';

export interface ActivityApi {
  overview(days: ActivityDays, signal?: AbortSignal): Promise<ActivityOverview>;
  sessions(query: ActivitySessionsQuery, signal?: AbortSignal): Promise<ActivitySessionPage>;
  session(key: ActivitySessionKey, signal?: AbortSignal): Promise<ActivitySessionReport>;
}
