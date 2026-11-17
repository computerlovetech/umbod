import { adminApi } from '#lib/admin/infrastructure/admin-api.js';
import { agentBehaviourApi } from '#lib/agent-behaviour/infrastructure/api.js';
import { InsightsState } from './insights-state.svelte';

export function createInsightsState(): InsightsState {
  return new InsightsState(agentBehaviourApi(), adminApi().analytics);
}
