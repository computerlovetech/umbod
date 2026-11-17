import { untrack } from 'svelte';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import type { WorkspaceAccessState } from './workspace-access-state.svelte';

export class WorkspaceScope {
  private readonly disposals = new Set<() => void>();

  constructor(readonly access: WorkspaceAccessState) {}

  registerDisposal = (dispose: () => void): (() => void) => {
    this.disposals.add(dispose);
    return (): void => { this.disposals.delete(dispose); };
  };

  dispose = (): void => {
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
