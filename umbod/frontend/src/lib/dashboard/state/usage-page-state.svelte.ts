import type { HeaderAccountIdentityState } from '$lib/header/accountIdentity';
import type { UsagePort } from '../api';
import { UsageState } from './usage-state.svelte';

export class UsagePageState {
  readonly usage: UsageState;
  private observedAccount: string | undefined;
  private active = true;

  constructor(port: UsagePort) {
    this.usage = new UsageState(port, this.authenticationLost);
  }

  observeAccountIdentity = (identity: HeaderAccountIdentityState, sourceChanged = false): void => {
    const account = identity.kind === 'visible' ? identity.hiddenValues.id : '';
    const previous = this.observedAccount;
    this.observedAccount = account;
    if (!this.active || previous === undefined || (previous === account && !sourceChanged)) return;
    this.usage.setIdentitySourceAvailable(account !== '');
    this.authenticationLost();
    if (account) void this.usage.revalidate();
  };

  authenticationLost = (): void => {
    this.usage.authenticationLost();
  };

  refreshOnFocus = async (): Promise<void> => {
    if (this.active) await this.usage.revalidate();
  };

  dispose = (): void => {
    this.active = false;
    this.usage.dispose();
  };
}
