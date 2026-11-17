import { describe, expect, test } from 'vitest';
import { clientRequestSchema, clientResponseSchema, policySchema, settingsSchema } from './schemas';

describe('automatic confidential client contract', (): void => {
  test.each(['client_secret_basic', 'client_secret_post'] as const)('accepts %s without manual credentials or configured-secret flags', (method): void => {
    const client = { kind: 'dynamic_confidential', token_endpoint_auth_method: method };
    for (const schema of [clientRequestSchema, clientResponseSchema]) {
      expect(schema.parse(client)).toEqual(client);
      expect(schema.parse({ ...client, approved_issuers: [] })).toEqual({ ...client, approved_issuers: [] });
      expect(schema.parse({ ...client, approved_issuers: ['https://Issuer.test:443/Exact/'] })).toEqual({ ...client, approved_issuers: ['https://Issuer.test:443/Exact/'] });
    }
    expect(settingsSchema.parse({ requested_scopes: ['write', 'read'], client })).toEqual({ requested_scopes: ['read', 'write'], client });
    expect(policySchema.parse({ connector_id: 'dinero', revision: 'r1', requested_scopes: [], client }).client).toEqual(client);
  });

  test.each([
    { token_endpoint_auth_method: undefined },
    { token_endpoint_auth_method: 'none' },
    { token_endpoint_auth_method: 'private_key_jwt' },
    { approved_issuers: ['https://one.test', 'https://two.test'] },
    { approved_issuers: ['http://issuer.test'] },
    { approved_issuers: null },
    { client_id: 'app' },
    { client_secret: 'secret' },
    { client_secret_configured: true },
    { issuer_url: 'https://issuer.test' }
  ])('rejects invalid automatic confidential fields %j', (fields): void => {
    const client = { kind: 'dynamic_confidential', token_endpoint_auth_method: 'client_secret_basic', ...fields };
    for (const schema of [clientRequestSchema, clientResponseSchema]) expect(schema.safeParse(client).success).toBe(false);
    expect(settingsSchema.safeParse({ requested_scopes: [], client }).success).toBe(false);
    expect(policySchema.safeParse({ connector_id: 'dinero', revision: 'r1', requested_scopes: [], client }).success).toBe(false);
  });
});
