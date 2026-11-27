import { usageSummaryFixture } from '#lib/dashboard/usage-fixtures.test-support.js';
import { vi } from 'vitest';
import type { ActivityApi } from './domain/activity-api.js';
import type { ActivityDays, ActivityOverview } from './domain/activity-schemas.js';

export function activityOverview(identityKey: string, days: ActivityDays, mcpSuccesses: number): ActivityOverview {
  const summary = usageSummaryFixture(days, mcpSuccesses);
  return {
    identity_key: identityKey,
    period: { days, as_of: summary.as_of, window: { start: `${summary.range.start}T00:00:00Z`, end: `${summary.range.end}T00:00:00Z` } },
    harness: { status: 'available', summary: { outcomes: { success: 0, failure: 0, unknown: 0 }, top_tools: [], skill_activations: 0 } },
    mcp: { status: 'available', summary }
  };
}

export function dashboardActivityApi(identityKey: string, mcpSuccesses: number): { [K in keyof ActivityApi]: ReturnType<typeof vi.fn<ActivityApi[K]>> } {
  return {
    overview: vi.fn<ActivityApi['overview']>().mockImplementation(async (days) => activityOverview(identityKey, days, mcpSuccesses)),
    sessions: vi.fn<ActivityApi['sessions']>().mockImplementation(async ({ days }) => ({
      identity_key: identityKey,
      period: activityOverview(identityKey, days ?? 7, 0).period,
      sessions: [],
      page: { kind: 'end' }
    })),
    session: vi.fn<ActivityApi['session']>()
  };
}
