import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';

export class DashboardIdentityProps {
  private currentIdentity = $state<HeaderAccountIdentityState>({ kind: 'hidden' });

  constructor(identity: HeaderAccountIdentityState) {
    this.currentIdentity = identity;
  }

  get identity(): HeaderAccountIdentityState { return this.currentIdentity; }

  replace = (identity: HeaderAccountIdentityState): void => {
    this.currentIdentity = identity;
  };
}
