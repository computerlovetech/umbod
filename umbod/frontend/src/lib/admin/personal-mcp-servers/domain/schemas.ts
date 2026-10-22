import { z } from 'zod';
import { downstreamMcpConnectorCreateInputSchema, downstreamMcpConnectorSchema } from '../../downstream-mcp-connectors';

export const scopesSchema = z.array(z.string().min(1).max(256).regex(/^[\x21\x23-\x5b\x5d-\x7e]+$/)).max(64)
  .refine((scopes) => new Set(scopes).size === scopes.length && scopes.join(' ').length <= 4096)
  .transform((scopes) => [...scopes].sort());
export const clientTextSchema = z.string().min(1).max(4096).refine((value) => value.trim().length > 0 && !/[\x00-\x1f\x7f]/.test(value));
export const issuerSchema = z.string().min(1).max(4096).refine((value) => {
  try {
    const url = new URL(value);
    const authority = value.split('/')[2] ?? '';
    return /^https:\/\//i.test(value) && url.protocol === 'https:' && !!url.hostname && !authority.includes('@') && !url.username && !url.password && !/[?#\\\s\x00-\x20\x7f-\uffff]/.test(value) && !authority.includes('%') && url.port !== '0' && !/[\x00-\x1f\x7f]/.test(decodeURIComponent(value));
  } catch { return false; }
});
const dynamicClientSchema = z.object({ kind: z.literal('dynamic_public') }).strict();
const publicClientSchema = z.object({ kind: z.literal('preconfigured_public'), issuer_url: issuerSchema, client_id: clientTextSchema }).strict();
const confidentialFields = { kind: z.literal('preconfigured_confidential'), issuer_url: issuerSchema, client_id: clientTextSchema, token_endpoint_auth_method: z.enum(['client_secret_basic', 'client_secret_post']) };
export const clientRequestSchema = z.discriminatedUnion('kind', [dynamicClientSchema, publicClientSchema, z.object({ ...confidentialFields, client_secret: clientTextSchema }).strict()]);
export const clientResponseSchema = z.discriminatedUnion('kind', [dynamicClientSchema, publicClientSchema, z.object({ ...confidentialFields, client_secret_configured: z.literal(true) }).strict()]);
export const settingsSchema = z.object({ requested_scopes: scopesSchema, client: clientRequestSchema }).strict();
export const policySchema = z.object({ connector_id: z.string().min(1), revision: z.string().min(1).max(128), requested_scopes: scopesSchema, client: clientResponseSchema }).strict();
export const replacePolicySchema = z.object({ expected_revision: z.string().min(1).max(128), settings: settingsSchema }).strict();
export const endpointSchema = z.string().url().refine((value) => {
  try {
    const url = new URL(value);
    return /^https:\/\//i.test(value) && !!url.hostname && !(value.split('/')[2] ?? '').includes('@') && !value.includes('#') && !/[\\\x00-\x20\x7f]/.test(value) && url.port !== '0';
  } catch { return false; }
});
export const createPersonalServerSchema = z.object({ metadata: downstreamMcpConnectorCreateInputSchema.shape.metadata, configuration: z.object({ endpoint_url: endpointSchema, oauth_configuration: settingsSchema }).strict() }).strict();
export const personalServerSchema = downstreamMcpConnectorSchema.refine((server) => server.authorization_mode === 'personal' && server.auth_mode === 'oauth');
export type PersonalPolicy = z.infer<typeof policySchema>;
export type PersonalSettings = z.infer<typeof settingsSchema>;
export type PersonalServerCreate = z.infer<typeof createPersonalServerSchema>;
export type PersonalPolicyReplace = z.infer<typeof replacePolicySchema>;
export type ClientKind = PersonalSettings['client']['kind'];

export function parseScopeText(value: string): string[] {
  if (/[^\x20-\x7e]/.test(value)) throw new Error('Invalid scope text');
  return scopesSchema.parse(value.trim() === '' ? [] : value.trim().split(/ +/));
}
