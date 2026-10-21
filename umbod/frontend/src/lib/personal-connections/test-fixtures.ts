import type { AuthorizationHealth, Attempt, Selection, StartAttempt } from './domain/schemas';

export const selection: Selection = {
  connector_id: 'calendar', display_name: 'Calendar', capability_description: 'Manage calendar',
  enabled: true, has_authorization: true, runtime_available: false,
  runtime_unavailable_reason: 'personal_oauth_not_supported'
};
export const authorizationHealth: AuthorizationHealth = { state: 'authorized', expires_at: '2030-01-01T00:00:00Z', refresh_supported: true };
export const pendingAttempt: StartAttempt = {
  attempt_id: 'attempt', status: 'pending', expires_at: '2030-01-01T00:00:00Z',
  authorization_url: 'https://provider.example/authorize?state=private'
};
export const completedAttempt: Attempt = {
  attempt_id: 'attempt', status: 'completed', expires_at: '2030-01-01T00:00:00Z'
};

export function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((success, failure) => { resolve = success; reject = failure; });
  return { promise, resolve, reject };
}
