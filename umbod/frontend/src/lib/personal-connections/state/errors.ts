import { renewalErrorSchema } from '../domain/schemas';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';

export function requiresSignIn(error: unknown): boolean {
  return error instanceof AuthenticationRequiredError || (error instanceof HttpError && error.status === 401);
}

export function isUnavailable(error: unknown): boolean {
  return error instanceof HttpError && [403, 404].includes(error.status);
}

export function safeRenewalError(error: unknown): string {
  const instruction = 'Check authorization status before another action. Do not retry renewal automatically.';
  if (!(error instanceof HttpError)) return `The renewal outcome could not be confirmed. ${instruction}`;
  const parsed = renewalErrorSchema.safeParse(error.body);
  if (!parsed.success) return `The renewal outcome could not be confirmed. ${instruction}`;
  const messages = {
    personal_refresh_unsupported: 'This authorization cannot be renewed here. Sign in again to replace it.',
    personal_refresh_conflict: 'Another authorization operation is in progress.',
    personal_refresh_changed: 'Authorization changed during renewal.',
    personal_refresh_reconnect_required: 'Sign in again is required.',
    personal_refresh_unavailable: 'Authorization renewal is unavailable. Its outcome could not be confirmed.',
    personal_refresh_invalid_request: 'The renewal request could not be accepted.'
  };
  return `${messages[parsed.data.detail.code]} ${instruction}`;
}

export function safeActionError(error: unknown): string {
  if (error instanceof NetworkError) return 'The outcome is unknown. Check authorization status before taking another action. Do not repeat a sign-in request automatically.';
  if (error instanceof HttpError && error.status === 409) return 'An operation conflicts with current state. An existing sign-in may need to be finished or expire. Check a known attempt or check authorization status; no attempt was replaced. An unknown attempt is never cancelled or restarted here.';
  if (isUnavailable(error)) return 'This connection or operation is not available for this account.';
  return 'The operation could not be completed. Check authorization status before trying another explicit action.';
}
