import { DashboardState } from '#lib/dashboard/state/dashboard-state.svelte.js';
import type { DashboardController } from '#lib/dashboard/state/port.js';
import { InMemoryDashboardApi } from '#lib/dashboard/infrastructure/in-memory-api.js';
import { catalogue } from '#lib/dashboard/test-fixtures.js';
import type { PersonalConnectionsApi } from '../api';
import { InMemoryAttemptScheduler } from '../infrastructure/in-memory-attempt-scheduler';

export function createPersonalDashboard(api: PersonalConnectionsApi): DashboardController {
  return new DashboardState(new InMemoryDashboardApi(catalogue), api, undefined, new InMemoryAttemptScheduler());
}
