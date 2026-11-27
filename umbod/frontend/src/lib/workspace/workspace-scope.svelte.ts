import { untrack } from 'svelte';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import type { WorkspaceAccessState } from './workspace-access-state.svelte';

export class WorkspaceScope {
  private readonly disposals = new Set<() => void>();
  private disposed = $state(false);
  private personalSuspended = $state(false);
  private personalRevision = 0;

  constructor(readonly access: WorkspaceAccessState) {}

  get personalIdentity(): HeaderAccountIdentityState {
    return this.disposed || this.personalSuspended ? { kind: 'hidden' } : this.access.effectiveAccountIdentity;
  }

  get verifiedPersonalIdentityKey(): string {
    const account = this.personalIdentity;
    return account.kind === 'visible' && account === this.access.accountIdentity ? account.hiddenValues.id : '';
  }

  get isPersonalSuspended(): boolean {
    return this.personalSuspended;
  }

  get personalChecking(): boolean {
    return !this.disposed && (this.personalSuspended || this.access.adminAccess === 'checking');
  }

  get personalUnavailable(): boolean {
    return !this.disposed && this.access.adminAccess === 'unavailable';
  }

  suspendPersonal = (): void => {
    this.personalRevision++;
    this.personalSuspended = true;
  };

  refreshPersonal = async (): Promise<void> => {
    if (this.disposed) return;
    this.suspendPersonal();
    const revision = this.personalRevision;
    await this.access.load();
    if (revision === this.personalRevision) this.personalSuspended = false;
  };

  registerDisposal = (dispose: () => void): (() => void) => {
    this.disposals.add(dispose);
    return (): void => { this.disposals.delete(dispose); };
  };

  dispose = (): void => {
    this.disposed = true;
    for (const dispose of this.disposals) dispose();
    this.disposals.clear();
    this.access.dispose();
  };
}

export class WorkspaceIdentityBinding {
  private version: number;

  constructor(
    private readonly access: WorkspaceAccessState,
    private readonly observeIdentity: (identity: HeaderAccountIdentityState, sourceChanged: boolean) => void
  ) {
    this.version = access.identitySourceVersion;
  }

  observe = (): void => {
    const version = this.access.identitySourceVersion;
    const identity = this.access.effectiveAccountIdentity;
    const changed = version !== this.version;
    this.version = version;
    untrack(() => this.observeIdentity(identity, changed));
  };
}
