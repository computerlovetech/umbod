import { describe, expect, test } from 'vitest';
import type { PersonalServerAdministration } from './administration';
import { InMemoryPersonalServers } from './in-memory';
import { clientRequestSchema, clientResponseSchema, issuerSchema, parseScopeText, policySchema, scopesSchema, settingsSchema, type PersonalSettings } from './domain/schemas';
import { createFixture, policyFixture, serverFixture } from './fixtures.test-support';

const clients: PersonalSettings['client'][] = [
  { kind: 'dynamic_public' },
  { kind: 'preconfigured_public', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'public' },
  { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test/Exact', client_id: 'client', token_endpoint_auth_method: 'client_secret_basic', client_secret: 'sentinel' },
  { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test/Exact', client_id: 'client', token_endpoint_auth_method: 'client_secret_post', client_secret: 'sentinel' }
];

describe('personal server administration port', () => {
  test.each(clients)('creates unpublished with a nonsecret policy for $kind', async (client) => {
    const api: PersonalServerAdministration = new InMemoryPersonalServers();
    const input = createFixture();
    input.configuration.oauth_configuration = { requested_scopes: ['z', 'A'], client };
    const server = await api.create(input);
    expect(server.publication_status).toBe('unpublished');
    expect(server.health.status).toBe('unknown');
    expect(server.credential_configured).toBe(false);
    const policy = await api.policy(server.connector_id);
    expect(policy.requested_scopes).toEqual(['A', 'z']);
    expect(JSON.stringify([server, policy, await api.list()])).not.toContain('sentinel');
    if (client.kind === 'preconfigured_confidential') expect(policy.client).toMatchObject({ client_secret_configured: true, token_endpoint_auth_method: client.token_endpoint_auth_method });
  });
  test('publication does not require tools and replacement preserves publication', async () => {
    const api: PersonalServerAdministration = new InMemoryPersonalServers();
    const server = await api.create(createFixture());
    await api.publish(server.connector_id);
    const original = await api.policy(server.connector_id);
    const next = await api.replacePolicy(server.connector_id, { expected_revision: original.revision, settings: { requested_scopes: ['read'], client: { kind: 'dynamic_public' } } });
    expect(next.revision).not.toBe(original.revision);
    expect((await api.get(server.connector_id)).publication_status).toBe('published');
    await api.withdraw(server.connector_id);
    expect((await api.get(server.connector_id)).publication_status).toBe('unpublished');
    await api.delete(server.connector_id);
    expect(await api.list()).toEqual([]);
    await expect(api.policy(server.connector_id)).rejects.toMatchObject({ status: 404 });
  });
  test('rejects stale concurrent policies without overwriting the winner', async () => {
    const api: PersonalServerAdministration = new InMemoryPersonalServers([serverFixture()], [policyFixture()]);
    const results = await Promise.allSettled(['read', 'write'].map((scope) => api.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [scope], client: { kind: 'dynamic_public' } } })));
    expect(results.filter((result) => result.status === 'fulfilled')).toHaveLength(1);
    expect(results.filter((result) => result.status === 'rejected')).toHaveLength(1);
    expect((await api.policy('personal')).requested_scopes).toEqual(['read']);
  });
  test('unchanged public settings are a no-op and confidential saves rotate', async () => {
    const api: PersonalServerAdministration = new InMemoryPersonalServers([serverFixture()], [policyFixture()]);
    const unchanged = await api.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'dynamic_public' } } });
    expect(unchanged.revision).toBe('r1');
    const rotated = await api.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: clients[2] } });
    const again = await api.replacePolicy('personal', { expected_revision: rotated.revision, settings: { requested_scopes: [], client: clients[2] } });
    expect(again.revision).not.toBe(rotated.revision);
  });
  test('grant-blocked deletion leaves records and policies intact', async () => {
    const api: PersonalServerAdministration = new InMemoryPersonalServers([serverFixture()], [policyFixture()], new Set(['personal']));
    await expect(api.delete('personal')).rejects.toMatchObject({ status: 409, body: { detail: { code: 'downstream_connector_grants_conflict' } } });
    expect(await api.list()).toHaveLength(1);
    expect(await api.policy('personal')).toEqual(policyFixture());
  });
});

describe('strict personal OAuth boundaries', () => {
  test.each(['read read', 'read\u00a0write', 'read\nwrite', 'read\twrite', 'read"write', 'read\\write', 'réad'])('rejects invalid human scope text %j', (value) => {
    expect(() => parseScopeText(value)).toThrow();
  });
  test('canonicalizes case-sensitive scopes without expanding non-ASCII whitespace', () => {
    expect(parseScopeText(' z A read Read ')).toEqual(['A', 'Read', 'read', 'z']);
    expect(parseScopeText('')).toEqual([]);
    expect(scopesSchema.safeParse(Array.from({ length: 65 }, (_, index) => `s${index}`)).success).toBe(false);
    expect(scopesSchema.safeParse(['a'.repeat(257)]).success).toBe(false);
    expect(scopesSchema.safeParse(Array.from({ length: 17 }, (_, index) => `${index}${'x'.repeat(250)}`)).success).toBe(false);
  });
  test.each(['http://issuer.test', 'https://name@issuer.test', 'https://issuer.test?q', 'https://issuer.test#', 'https://issuer.test/\npath', 'https://issuer.test/%0a', 'https://issuer.test:0', 'https://iss%75er.test', 'https://issuer.test\\path'])('rejects unsafe issuer %s', (value) => {
    expect(issuerSchema.safeParse(value).success).toBe(false);
  });
  test.each(['', ' ', 'a\nb', 'a\u007fb', 'x'.repeat(4097)])('rejects invalid identifiers and fresh secrets', (value) => {
    expect(clientRequestSchema.safeParse({ ...clients[2], client_id: value }).success).toBe(false);
    expect(clientRequestSchema.safeParse({ ...clients[2], client_secret: value }).success).toBe(false);
  });
  test('separates response projections from confidential write secrets', () => {
    const client = clients[2];
    const projection = { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'id', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true };
    expect(clientResponseSchema.safeParse(client).success).toBe(false);
    expect(clientRequestSchema.safeParse(projection).success).toBe(false);
    expect(clientResponseSchema.safeParse({ ...projection, client_secret: '********' }).success).toBe(false);
    expect(clientResponseSchema.safeParse({ ...projection, client_secret_configured: false }).success).toBe(false);
    expect(settingsSchema.safeParse({ requested_scopes: [], client: { kind: 'dynamic_public', client_secret: 'secret' } }).success).toBe(false);
    expect(policySchema.safeParse({ ...policyFixture(), client }).success).toBe(false);
    expect(issuerSchema.parse('https://Issuer.test:443/Exact/')).toBe('https://Issuer.test:443/Exact/');
  });
});
