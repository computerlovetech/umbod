import { z } from 'zod';
import { issuerSchema, scopesSchema } from './schemas';

export const setupRequestSchema = z.object({ expected_revision: z.string().min(1).max(128) }).strict();
export const setupDiscoverySchema = z.object({
  issuer_url: issuerSchema,
  redirect_uri: z.string().url(),
  available_scopes: scopesSchema,
  registration_mode: z.enum(['dynamic_public', 'dynamic_confidential', 'preconfigured_public', 'preconfigured_confidential'])
}).strict();
const resultFields = { discovery: setupDiscoverySchema, returned_scopes: scopesSchema };
const completedFields = { checked_at: z.string().datetime({ offset: true }) };
const responseEvidenceSchema = z.discriminatedUnion('kind', [z.object({ kind: z.literal('no_response') }).strict(), z.object({ kind: z.literal('http_response'), status_code: z.number().int().min(100).max(599) }).strict()]);
export const setupStateSchema = z.discriminatedUnion('status', [
  z.object({ status: z.literal('required') }).strict(),
  z.object({ status: z.literal('in_progress'), operation: z.enum(['discovery', 'validation']), attempt_id: z.string().min(1), lease_expires_at: z.string().datetime({ offset: true }) }).strict(),
  z.object({ status: z.literal('discovered'), ...completedFields, discovery: setupDiscoverySchema }).strict(),
  z.object({ status: z.literal('validated'), ...completedFields, result: z.object({ kind: z.literal('validated'), ...resultFields, scope_source: z.enum(['registration', 'not_returned', 'not_checked']) }).strict() }).strict(),
  z.object({ status: z.literal('scope_mismatch'), ...completedFields, result: z.object({ kind: z.literal('scope_mismatch'), ...resultFields, downstream_response: responseEvidenceSchema }).strict() }).strict(),
  z.object({ status: z.literal('failed'), ...completedFields, stage: z.enum(['discovery', 'registration', 'token_exchange', 'refresh']), reason: z.enum(['provider_rejected', 'timeout', 'invalid_response', 'network_failure', 'unexpected_failure', 'unsupported', 'scope_mismatch', 'resource_mismatch', 'issuer_mismatch', 'ambiguous_issuer', 'pkce_s256_required', 'authorization_code_required', 'code_response_required', 'client_auth_required', 'registration_unavailable', 'registration_contract_mismatch']) }).strict()
]);
export const setupStatusSchema = z.object({ connector_id: z.string().min(1), revision: z.string().min(1), policy_revision: z.string().min(1), redirect_uri: z.string().url(), state: setupStateSchema }).strict();
export type SetupRequest = z.infer<typeof setupRequestSchema>;
export type SetupStatus = z.infer<typeof setupStatusSchema>;
export type SetupDiscovery = z.infer<typeof setupDiscoverySchema>;
