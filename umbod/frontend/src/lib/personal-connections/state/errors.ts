import { discoveryErrorSchema, oauthInitiationErrorSchema, oauthScopeMismatchErrorSchema, renewalErrorSchema, type OAuthScopeMismatch } from '../domain/schemas';
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

export type ScopeMismatchAudience = 'administrator' | 'user';

const quotedScopes = (scopes: readonly string[]): string => scopes.map((scope) => `“${scope}”`).join(', ');

export function scopeMismatch(error: unknown): OAuthScopeMismatch | null {
  if (!(error instanceof HttpError) || error.status !== 422) return null;
  const parsed = oauthScopeMismatchErrorSchema.safeParse(error.body);
  return parsed.success ? parsed.data.detail : null;
}

export function scopeMismatchExplanation(mismatch: OAuthScopeMismatch, connectorName: string, audience: ScopeMismatchAudience): string {
  if (audience === 'user') {
    return 'Could not start sign-in because this MCP server’s scope settings prevent sign-in. Ask an administrator to update its Requested scopes setting.';
  }
  const returned = mismatch.returned_scopes.length ? `scope ${quotedScopes(mismatch.returned_scopes)}` : 'no scopes';
  const configured = mismatch.configured_scopes.length
    ? `but Umbod requested ${quotedScopes(mismatch.configured_scopes)}`
    : 'but no scopes were configured in Umbod';
  return `Could not start sign-in. “${connectorName}” returned ${returned} during client registration, ${configured}. Update this connector’s Requested scopes setting to match the scopes it needs.`;
}

export function safeActionError(error: unknown): string {
  if (error instanceof NetworkError) return 'The outcome is unknown. Check authorization status before taking another action. Do not repeat a sign-in request automatically.';
  if (error instanceof HttpError && error.status === 409 && discoveryErrorSchema.safeParse(error.body).success) {
    return 'Tool discovery could not be completed. Check authorization status before trying again.';
  }
  if (error instanceof HttpError && error.status === 409) return 'Another operation is in progress. Check the known sign-in attempt or authorization status. No attempt was replaced; unknown attempts cannot be cancelled or restarted here.';
  if (isUnavailable(error)) return 'This MCP server or operation is unavailable.';
  const mismatch = scopeMismatch(error);
  if (mismatch) return scopeMismatchExplanation(mismatch, '', 'user');
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
