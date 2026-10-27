import type { PersonalConnectionController } from './state/port';

export type ConnectionAction = 'retry-tools' | 'connect' | 'toggle' | 'sign-in' | 'discover' | 'renew' | 'refresh' | 'check' | 'cancel' | 'disconnect';
export type AccessTone = 'success' | 'warning' | 'neutral' | 'pending';

export interface AccessStatus {
  readonly label: string;
  readonly description: string;
  readonly tone: AccessTone;
  readonly action: ConnectionAction | null;
}

export interface ConnectionMenuAction {
  readonly id: ConnectionAction;
  readonly label: string;
  readonly disabled: boolean;
  readonly reason: string;
  readonly destructive: boolean;
}

export interface PersonalAccessViewController {
  readonly status: AccessStatus;
  readonly primaryLabel: string;
  readonly primaryDisabled: boolean;
  readonly menuOpen: boolean;
  readonly menuActions: ConnectionMenuAction[];
  readonly fallbackRequired: boolean;
  setMenuOpen(open: boolean): void;
  perform(action: ConnectionAction): Promise<void>;
}

const reconnectDescriptions = {
  provider_rejected: 'The provider rejected this authorization. Sign in again to restore access.',
  refresh_denied: 'Authorization renewal was rejected. Sign in again to restore access.',
  refresh_uncertain: 'The renewal outcome could not be confirmed. Sign in again to restore access.'
};

export function personalAccessStatus(state: PersonalConnectionController): AccessStatus {
  if (state.loadingTools) return { label: 'Loading tools', description: 'Loading your personal tools.', tone: 'pending', action: null };
  if (state.toolsRecovery && state.selection.enabled && !state.busy) return { label: 'Tools not ready', description: 'Your authorization is saved. Retry loading tools to check access and continue.', tone: 'warning', action: 'retry-tools' };
  if (state.needsRefresh) return { label: 'Status needs checking', description: 'The last action could not be confirmed. Check authorization status before continuing.', tone: 'warning', action: 'refresh' };
  if (state.busy) return {
    label: state.renewing ? 'Renewing access…' : state.readingDetails ? 'Checking access…' : 'Updating access…',
    description: 'Please wait while your personal access is updated.', tone: 'pending', action: null
  };
  if (!state.selection.enabled) return { label: 'Disabled', description: 'Personal access is turned off. Enable it when you want to use this connector.', tone: 'neutral', action: 'connect' };
  if (state.attempt) {
    const fallback = Boolean(state.authorizationUrl && !state.authorizationOpened);
    return {
      label: state.checking ? 'Checking sign-in…' : fallback ? 'Sign-in needs attention' : 'Waiting for sign-in',
      description: fallback ? 'The sign-in window could not be opened automatically. Continue sign-in below. Your tools will load automatically when sign-in completes.' : 'Complete sign-in in the window or tab that opened. It will close automatically and your tools will load when sign-in completes.',
      tone: fallback && !state.checking ? 'warning' : 'pending', action: state.monitoring && !state.error ? null : 'check'
    };
  }
  if (state.healthPhase === 'loading') return { label: 'Checking access…', description: 'Checking your saved authorization and tool availability.', tone: 'pending', action: null };
  if (state.healthPhase !== 'ready' || !state.health) return { label: 'Status unavailable', description: 'Your authorization status could not be checked. Check status to try again.', tone: 'warning', action: 'refresh' };
  const health = state.health;
  if ((health.state === 'authorized' || health.state === 'expired') && !state.selection.has_authorization) return { label: 'Status needs checking', description: 'Your saved access details have changed. Check status before continuing.', tone: 'warning', action: 'refresh' };
  switch (health.state) {
    case 'not_authorized': return { label: 'Sign-in required', description: 'Sign in to connect your account and make your personal tools available.', tone: 'warning', action: 'sign-in' };
    case 'expired': return { label: 'Authorization expired', description: state.canRenew ? 'Your authorization has expired. Renew access to use this connector again.' : 'Your authorization has expired. Sign in again to restore access.', tone: 'warning', action: state.canRenew ? 'renew' : 'sign-in' };
    case 'unsupported': return { label: 'Sign-in required', description: 'Your saved authorization is no longer supported. Sign in again to replace it.', tone: 'warning', action: 'sign-in' };
    case 'reconnect_required': return { label: 'Sign-in required', description: reconnectDescriptions[health.reason], tone: 'warning', action: 'sign-in' };
    case 'refreshing': return { label: 'Renewal in progress', description: 'Renewal is already in progress. Check status before another action.', tone: 'pending', action: 'refresh' };
    case 'authorized': return state.selection.runtime_available && !state.toolsNeedLoading
      ? { label: 'Ready to use', description: 'Your authorization is valid and your personal tools are available.', tone: 'success', action: null }
      : { label: 'Tools not ready', description: 'Your authorization is valid, but tools are not available. Refresh tools, or contact your administrator if this continues.', tone: 'warning', action: 'discover' };
  }
}
