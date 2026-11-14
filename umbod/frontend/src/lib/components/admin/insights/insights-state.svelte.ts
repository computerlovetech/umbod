import type { AgentBehaviourPort } from '$lib/agent-behaviour/api';
import { AgentBehaviourPageState } from '$lib/agent-behaviour/state/page-state.svelte';
import { AnalyticsState } from '$lib/admin/analytics/analytics-state.svelte';
import type { LogCountSource } from '$lib/admin/analytics/port';

export class InsightsState {
  readonly behaviour: AgentBehaviourPageState;
  private analytics: AnalyticsState | undefined;
  private revoked = false;

  constructor(api: AgentBehaviourPort, private readonly logCounts: LogCountSource) {
    this.behaviour = new AgentBehaviourPageState(api, this.revoke);
  }

  get allowed(): boolean { return this.behaviour.allowed; }

  start = (): void => {
    if (!this.revoked) this.behaviour.start();
  };

  createAnalytics = (): AnalyticsState => {
    this.analytics?.dispose();
    this.analytics = new AnalyticsState(this.logCounts, () => new Date(), this.revoke);
    if (this.revoked) this.analytics.dispose();
    return this.analytics;
  };

  revoke = (): void => {
    if (this.revoked) return;
    this.revoked = true;
    this.behaviour.dispose();
    this.analytics?.dispose();
  };

  dispose = (): void => { this.revoke(); };
}
