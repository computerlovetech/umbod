import type { AgentBehaviourPort } from '../api';
import { ConfigurationState } from './configuration-state.svelte';
import { ReportsState } from './reports-state.svelte';

export class AgentBehaviourPageState {
  private accessAllowed = $state(true);
  private started = false;
  get allowed(): boolean { return this.accessAllowed; }
  readonly configuration: ConfigurationState;
  readonly reports: ReportsState;
  constructor(api: AgentBehaviourPort, private readonly onAccessLost?: () => void) {
    this.configuration = new ConfigurationState(api.configuration, this.revoke);
    this.reports = new ReportsState(api.reports, this.revoke, () => ({ patterns: this.configuration.publishedPatterns, playbooks: this.configuration.publishedPlaybooks }));
  }
  start = (): void => {
    if (this.started || !this.accessAllowed) return;
    this.started = true;
    void this.configuration.load();
  };
  revoke = (): void => {
    if (!this.accessAllowed) return;
    this.accessAllowed = false;
    this.configuration.dispose();
    this.reports.dispose();
    this.onAccessLost?.();
  };
  dispose = (): void => {
    this.accessAllowed = false;
    this.configuration.dispose();
    this.reports.dispose();
  };
}
