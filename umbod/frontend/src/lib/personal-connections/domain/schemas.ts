import { z } from 'zod';
import { capabilityDescriptionSchema } from '$lib/admin/capability-descriptions';

export const selectionSchema = z.object({
  connector_id: z.string(),
  display_name: z.string(),
  capability_description: capabilityDescriptionSchema,
  enabled: z.boolean(),
  has_authorization: z.boolean(),
  runtime_available: z.boolean(),
  runtime_unavailable_reason: z.enum(['', 'personal_oauth_not_supported'])
}).strict();
export const selectionListSchema = z.object({ connectors: z.array(selectionSchema) }).strict();
export const enablementRequestSchema = z.object({ enabled: z.boolean() }).strict();
export const emptyRequestSchema = z.object({}).strict();
export const attemptSchema = z.object({
  attempt_id: z.string(),
  status: z.enum(['preparing', 'pending', 'exchanging', 'completed', 'cancelled', 'failed', 'expired']),
  expires_at: z.iso.datetime({ offset: true })
}).strict();
export const authorizationUrlSchema = z.url().refine((value) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && url.username === '' && url.password === '';
  } catch {
    return false;
  }
});
export const startAttemptSchema = attemptSchema.extend({ authorization_url: authorizationUrlSchema }).strict();

export const authorizationHealthSchema = z.discriminatedUnion('state', [
  z.object({ state: z.literal('not_authorized') }).strict(),
  z.object({ state: z.literal('authorized'), expires_at: z.iso.datetime({ offset: true }), refresh_supported: z.boolean() }).strict(),
  z.object({ state: z.literal('expired'), expires_at: z.iso.datetime({ offset: true }), refresh_supported: z.boolean() }).strict(),
  z.object({ state: z.literal('unsupported') }).strict(),
  z.object({ state: z.literal('reconnect_required'), reason: z.enum(['provider_rejected', 'refresh_uncertain', 'refresh_denied']) }).strict(),
  z.object({ state: z.literal('refreshing'), deadline: z.iso.datetime({ offset: true }) }).strict()
]);
export const renewalResultSchema = z.object({ status: z.literal('refreshed'), discovery_required: z.literal(true) }).strict();
export const renewalErrorSchema = z.object({ detail: z.object({ code: z.enum([
  'personal_refresh_unsupported', 'personal_refresh_conflict', 'personal_refresh_changed',
  'personal_refresh_reconnect_required', 'personal_refresh_unavailable', 'personal_refresh_invalid_request'
]) }) });
export type AuthorizationHealth = z.infer<typeof authorizationHealthSchema>;
export type RenewalResult = z.infer<typeof renewalResultSchema>;

export type Selection = z.infer<typeof selectionSchema>;
export type SelectionList = z.infer<typeof selectionListSchema>;
export type EnablementRequest = z.infer<typeof enablementRequestSchema>;
export type EmptyRequest = z.infer<typeof emptyRequestSchema>;
export type Attempt = z.infer<typeof attemptSchema>;
export type StartAttempt = z.infer<typeof startAttemptSchema>;

export function isTerminalAttempt(attempt: Attempt): boolean {
  return ['completed', 'cancelled', 'failed', 'expired'].includes(attempt.status);
}
