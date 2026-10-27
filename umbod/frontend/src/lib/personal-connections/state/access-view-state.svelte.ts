import { personalAccessStatus, type AccessStatus, type ConnectionAction, type ConnectionMenuAction, type PersonalAccessViewController } from '../presentation';
import type { PersonalConnectionController } from './port';

export class PersonalAccessViewState implements PersonalAccessViewController {
  menuOpen = $state(false);
  root: HTMLDivElement | null = null;

  constructor(private readonly connection: () => PersonalConnectionController) {}

  get status(): AccessStatus {
    return personalAccessStatus(this.connection());
  }

  get signInLabel(): string {
    const state = this.connection();
    return state.selection.has_authorization || (state.health && ['expired', 'unsupported', 'reconnect_required'].includes(state.health.state)) ? 'Sign in again' : 'Sign in';
  }

  get healthLabel(): string {
    const state = this.connection();
    if (state.healthPhase === 'loading') return 'Checking authorization status…';
    if (state.healthPhase !== 'ready' || !state.health) return 'Authorization status unavailable';
    const labels = { not_authorized: 'Sign-in required', authorized: 'Authorization valid locally', expired: 'Authorization expired', unsupported: 'Unsupported authorization', reconnect_required: 'Sign-in required', refreshing: 'Renewal in progress' };
    return labels[state.health.state];
  }

  get menuActions(): ConnectionMenuAction[] {
    const state = this.connection();
    const blockedReason = state.needsRefresh ? 'Check authorization status before another action.' : state.busy || state.checking ? 'Another action is in progress.' : state.attempt ? 'Finish or cancel the current sign-in first.' : state.renewalInProgress ? 'Renewal is in progress. Check authorization status.' : this.status.description;
    const item = (id: ConnectionAction, label: string, disabled: boolean, destructive = false): ConnectionMenuAction => ({ id, label, disabled, reason: disabled ? blockedReason : '', destructive });
    return [
      ...(state.toolsRecovery && state.selection.enabled ? [item('retry-tools', 'Retry loading tools', state.busy || state.checking || state.attempt !== null)] : []),
      item('toggle', state.selection.enabled ? 'Disable access' : 'Enable access', state.selection.enabled ? state.cleanupBlocked : state.busy || state.needsRefresh),
      ...(state.selection.enabled ? state.attempt
        ? [item('continue-sign-in', 'Continue sign-in', !state.authorizationUrl || state.busy || state.needsRefresh)]
        : [item('sign-in', this.signInLabel, state.busy || state.checking || state.needsRefresh || state.renewalInProgress)] : []),
      ...(state.selection.enabled && state.selection.has_authorization ? [item('discover', 'Refresh tools', !state.canDiscover)] : []),
      ...(state.renewableAuthorization ? [item('renew', 'Renew access', !state.canRenew)] : []),
      item('refresh', 'Check authorization status', state.busy || state.checking || state.loadingTools),
      ...(state.attempt ? [item('check', 'Check sign-in status', state.busy || state.checking), item('cancel', 'Cancel sign-in', state.busy || state.needsRefresh)] : []),
      ...(state.selection.has_authorization || state.attempt ? [item('disconnect', 'Disconnect', state.cleanupBlocked, true)] : [])
    ];
  }

  setMenuOpen = (open: boolean): void => {
    this.menuOpen = open;
  };

  focusTrigger = (): void => {
    this.root?.querySelector<HTMLButtonElement>('button')?.focus();
  };

  perform = async (action: ConnectionAction): Promise<void> => {
    this.setMenuOpen(false);
    const item = this.menuActions.find((candidate) => candidate.id === action);
    if (!item || item.disabled) return;
    const state = this.connection();
    const operations: Record<ConnectionAction, () => Promise<void> | void> = {
      'retry-tools': () => state.retryLoadingTools(), 'continue-sign-in': () => state.continueSignIn(), toggle: () => state.setEnabled(), 'sign-in': () => state.start(), discover: () => state.discover(), renew: () => state.renew(), refresh: () => state.refresh(), check: () => state.check(), cancel: () => state.cancel(), disconnect: () => state.requestDisconnect()
    };
    await operations[action]();
  };
}
