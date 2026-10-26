import { DashboardState } from '$lib/dashboard/state/dashboard-state.svelte';
import type { DashboardController } from '$lib/dashboard/state/port';
import { InMemoryDashboardApi } from '$lib/dashboard/infrastructure/in-memory-api';
import { catalogue } from '$lib/dashboard/test-fixtures';
import type { PersonalConnectionsApi } from '../api';
import { InMemoryAttemptScheduler } from '../infrastructure/in-memory-attempt-scheduler';

export function createPersonalDashboard(api: PersonalConnectionsApi): DashboardController {
  return new DashboardState(new InMemoryDashboardApi(catalogue), api, undefined, new InMemoryAttemptScheduler());
}
