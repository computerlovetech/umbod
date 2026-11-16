import { describe, expect, test, vi } from 'vitest';
import { AdminApi } from '../infrastructure/admin-api';
import { browserTransport } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { discoveryFixture, setupFixture } from './setup.test-support';

function harness(response: unknown = setupFixture()): { api: AdminApi; request: ReturnType<typeof vi.fn<typeof fetch>> } {
  const request = vi.fn<typeof fetch>(async () => Response.json(response));
  const api = new AdminApi(browserTransport({ fetch: request, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' }) }));
  return { api, request };
}

describe('personal OAuth setup route', (): void => {
  test('status is read-only and provider operations send only the saved setup revision', async (): Promise<void> => {
    const { api, request } = harness({ ...setupFixture(), connector_id: 'a b' });
    await api.personalOAuthSetup.status('a b');
    await api.personalOAuthSetup.discover('a b', { expected_revision: 'setup-1' });
    await api.personalOAuthSetup.validate('a b', { expected_revision: 'setup-1' });
    expect(request.mock.calls.map(([path, init]) => [path, init?.method, init?.body])).toEqual([
      ['/api/admin/connectors/mcp/a%20b/personal-oauth/setup', 'GET', undefined],
      ['/api/admin/connectors/mcp/a%20b/personal-oauth/setup/discovery', 'POST', '{"expected_revision":"setup-1"}'],
      ['/api/admin/connectors/mcp/a%20b/personal-oauth/setup/validation', 'POST', '{"expected_revision":"setup-1"}']
    ]);
  });

  test.each(['discover', 'validate'] as const)('%s validates outgoing bodies before network and has no automatic retry', async (operation): Promise<void> => {
    const { api, request } = harness();
    await expect(api.personalOAuthSetup[operation]('personal', { expected_revision: '' })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
    request.mockRejectedValueOnce(new Error('provider-secret'));
    await expect(api.personalOAuthSetup[operation]('personal', { expected_revision: 'r1' })).rejects.toThrow();
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    { ...setupFixture(), connector_id: 'someone-else' },
    { ...setupFixture(), state: { status: 'validated', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'validated', discovery: discoveryFixture(), returned_scopes: [], scope_source: 'registration', client_secret: 'provider-secret' } } },
    { ...setupFixture(), state: { status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'registration', reason: 'provider-secret' } }
  ])('rejects mismatched ownership and unapproved provider data', async (response): Promise<void> => {
    const { api } = harness(response);
    await expect(api.personalOAuthSetup.validate('personal', { expected_revision: 'r1' })).rejects.toMatchObject({ direction: 'inbound' });
  });

  test('accepts completed safe scope mismatch evidence and timestamp', async (): Promise<void> => {
    const response = setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00+00:00', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: ['records:read'], downstream_response: { kind: 'http_response', status_code: 201 } } });
    const { api } = harness(response);
    expect(await api.personalOAuthSetup.validate('personal', { expected_revision: 'r1' })).toEqual(response);
  });
});
