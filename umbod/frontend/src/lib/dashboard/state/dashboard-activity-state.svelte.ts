import { untrack } from 'svelte';
import type { WorkspaceScope } from '#lib/workspace/workspace-scope.svelte.js';
import { ActivityState } from '#lib/insights/activity/activity-state.svelte.js';
import type { ActivityApi } from '#lib/insights/activity/domain/activity-api.js';

export class DashboardActivityState {
  private owned = $state.raw<{ key: string; activity: ActivityState }>();
  private started = $state(false);
  checking = $state(false);
  private validationRevision = 0;
  private sourceVersion?: number;

  constructor(private readonly api: ActivityApi, private readonly workspace: WorkspaceScope) {}

  get activity(): ActivityState | undefined {
    const { key, activity } = this.owned ?? {};
    return this.started && key === this.currentIdentity() ? activity : undefined;
  }

  start = (visible: boolean): void => {
    this.started = true;
    if (!visible) this.suspend();
    else if (this.workspace.isPersonalSuspended) void this.revalidate();
  };

  observeAccount = (): void => {
    if (!this.started) return;
    const key = this.currentIdentity();
    const version = this.workspace.access.identitySourceVersion;
    untrack((): void => {
      if (this.sourceVersion !== version || (key && key !== this.owned?.key)) {
        this.owned?.activity.dispose();
        this.owned = key ? { key, activity: new ActivityState(this.api, key, this.currentIdentity) } : undefined;
      }
      this.sourceVersion = version;
      const activity = this.owned?.activity;
      if (key) void activity?.refresh();
      else activity?.suspend();
    });
  };

  private currentIdentity = (): string => this.started && !this.checking ? this.workspace.verifiedPersonalIdentityKey : '';

  observeVisibility = (visible: boolean): void => {
    if (!this.started) return;
    if (visible) void this.revalidate();
    else this.suspend();
  };

  private suspend(): number {
    this.checking = true;
    this.owned?.activity.suspend();
    return ++this.validationRevision;
  }

  revalidate = async (): Promise<void> => {
    if (!this.started) return;
    const revision = this.suspend();
    if (this.workspace.isPersonalSuspended) await this.workspace.refreshPersonal();
    else await this.workspace.access.load();
    if (revision === this.validationRevision) this.checking = false;
  };

  dispose = (): void => {
    this.validationRevision++;
    this.started = false;
    this.owned?.activity.dispose();
    this.owned = undefined;
  };
}
