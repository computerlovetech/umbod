import { discoveryErrorSchema, oauthInitiationErrorSchema, renewalErrorSchema } from '../domain/schemas';
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
  if (error instanceof HttpError && error.status === 409 && discoveryErrorSchema.safeParse(error.body).success) {
    return 'Tool discovery could not be completed. Check authorization status before trying again.';
  }
  if (error instanceof HttpError && error.status === 409) return 'Another operation is in progress. Check the known sign-in attempt or authorization status. No attempt was replaced; unknown attempts cannot be cancelled or restarted here.';
  if (isUnavailable(error)) return 'This MCP server or operation is unavailable.';
  if (error instanceof HttpError && error.status === 422) {
    const parsed = oauthInitiationErrorSchema.safeParse(error.body);
    if (parsed.success) {
      const messages = {
        personal_oauth_provider_unsupported: 'Could not start sign-in. An administrator must check this MCP server’s OAuth compatibility.',
        personal_oauth_invalid_request: 'Sign-in request rejected.'
      };
      return `${messages[parsed.data.detail.code]} Check authorization status before another action.`;
    }
  }
  return 'Operation failed. Check authorization status before another action.';
}
