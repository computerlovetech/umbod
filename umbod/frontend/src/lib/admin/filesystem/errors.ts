import { z } from 'zod';
import { AuthenticationRequiredError, HttpError } from '../infrastructure/transport';

const policyErrorSchema = z.object({ detail: z.object({ code: z.string() }) });
export function policyErrorCode(error: unknown): string {
  if (!(error instanceof HttpError)) return '';
  const parsed = policyErrorSchema.safeParse(error.body);
  return parsed.success ? parsed.data.detail.code : '';
}
export function policyErrorMessage(error: unknown): string {
  if (error instanceof AuthenticationRequiredError) return 'Your session has expired. Sign in again before reloading.';
  if (error instanceof HttpError && error.status === 403) return 'Administrator access is required.';
  if (policyErrorCode(error) === 'filesystem_policy_stale') return 'The root policy changed. Your unsaved draft is preserved. Reload explicitly before saving again.';
  if (policyErrorCode(error) === 'filesystem_policy_conflict') return 'The filesystem policy conflicts with this editor. Ask an operator to resolve the root ownership or recursive policy conflict, then reload.';
  if (policyErrorCode(error) === 'filesystem_policy_storage_failure') return 'The filesystem policy could not be stored. Reload to verify the saved policy before trying again.';
  return 'The filesystem policy could not be loaded or saved. Reload to verify the saved policy before trying again.';
}
