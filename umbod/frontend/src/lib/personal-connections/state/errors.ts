import { discoveryErrorSchema, oauthInitiationErrorSchema, oauthProviderFailureSchema, renewalErrorSchema } from '../domain/schemas';
import { AuthenticationRequiredError, HttpError, NetworkError } from '#lib/admin/infrastructure/transport.js';

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
  if (error instanceof HttpError && error.status === 502) {
    const parsed = oauthProviderFailureSchema.safeParse(error.body);
    if (parsed.success) {
      const rejectionMessages = {
        discovery: 'The provider rejected OAuth discovery. Ask an administrator to check the provider and OAuth configuration.',
        registration: 'The provider rejected client registration. Ask an administrator to check the OAuth configuration.',
        token_exchange: 'The provider rejected the token exchange. Check authorization status before signing in again.',
        refresh: 'Operation failed.'
      };
      const messages = {
        provider_rejected: rejectionMessages[parsed.data.detail.stage],
        timeout: 'The provider did not respond in time.',
        invalid_response: 'The provider returned an invalid response. Ask an administrator to check OAuth compatibility.',
        network_failure: 'The provider could not be reached.',
        unexpected_failure: 'Operation failed.'
      };
      if (messages[parsed.data.detail.reason] !== 'Operation failed.') {
        return `${messages[parsed.data.detail.reason]} Check authorization status before another action. Do not retry automatically.`;
      }
    }
  }
  return 'Operation failed. Check authorization status before another action.';
}
