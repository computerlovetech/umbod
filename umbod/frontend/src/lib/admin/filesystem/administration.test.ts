import { describe, expect, it, vi } from 'vitest';
import { InMemoryFilesystemAdministration } from './in-memory';
import { rootPolicy } from './fixtures.test-support';
import { FilesystemRoute } from './http-route';
import { browserTransport, SchemaValidationError } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { replaceRootAccessSchema, rootAccessSchema } from './domain/schemas';
import { policyErrorMessage } from './errors';

const grant = { group_id: ' exact group ', permissions: ['read' as const] };

describe('filesystem administration contract', () => {
  it('initializes, persists exact IDs, clears configurable permissions and rejects stale revisions', async (): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ blocked_group_ids: ['operator-managed'] }));
    const empty = await api.replaceRootAccess({ expected_revision: 'initial', groups: [] });
    expect(empty.status).toBe('ready');
    const saved = await api.replaceRootAccess({ expected_revision: empty.revision, groups: [grant] });
    expect(saved.groups).toEqual([grant]);
    const cleared = await api.replaceRootAccess({ expected_revision: saved.revision, groups: [] });
    expect(cleared.groups).toEqual([]);
    expect(cleared.blocked_group_ids).toEqual(['operator-managed']);
    await expect(api.replaceRootAccess({ expected_revision: 'initial', groups: [] })).rejects.toMatchObject({ status: 409, body: { detail: { code: 'filesystem_policy_stale' } } });
  });
  it.each([
    [{ ...grant, group_id: ' ' }],
    [{ ...grant, permissions: [] }],
    [{ ...grant, permissions: ['invalid'] }],
    [{ ...grant, permissions: ['read', 'read'] }],
    [grant, grant],
    [{ ...grant, issuer: 'forbidden' }]
  ])('rejects malformed or duplicate groups %j', (...groups): void => {
    expect(replaceRootAccessSchema.safeParse({ expected_revision: '', groups }).success).toBe(false);
    expect(rootAccessSchema.safeParse({ ...rootPolicy(), groups }).success).toBe(false);
  });
  it('preserves whitespace and distinguishes exact group IDs', (): void => {
    const groups = [grant, { ...grant, group_id: 'exact group' }];
    expect(replaceRootAccessSchema.parse({ expected_revision: '', groups }).groups).toEqual(groups);
  });
  it.each(['issuer', 'root_id', 'suggested_issuer', 'group_claim', 'unmanaged_groups', 'owner'])('strictly rejects extra %s fields', (field): void => {
    expect(rootAccessSchema.safeParse({ ...rootPolicy(), [field]: 'forbidden' }).success).toBe(false);
    expect(replaceRootAccessSchema.safeParse({ expected_revision: '', groups: [], [field]: 'forbidden' }).success).toBe(false);
  });
  it.each(['conflict', 'blocked'] as const)('rejects %s assignment', async (kind): Promise<void> => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: kind === 'conflict' ? 'conflict' : 'ready', blocked_group_ids: kind === 'blocked' ? [grant.group_id] : [] }));
    await expect(api.replaceRootAccess({ expected_revision: 'initial', groups: [grant] })).rejects.toMatchObject({ status: 409 });
  });
});

describe('filesystem HTTP boundary', () => {
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  it('validates GET and PUT and sends only the editable projection', async (): Promise<void> => {
    const policy = rootPolicy({ groups: [grant], blocked_group_ids: ['blocked'] });
    const request = vi.fn<typeof fetch>().mockImplementation(async (): Promise<Response> => new Response(JSON.stringify(policy)));
    const api = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    expect(await api.getRootAccess()).toEqual(policy);
    expect(request.mock.calls[0][0]).toBe('/api/admin/filesystem/root-access');
    const body = { expected_revision: 'initial', groups: [grant] };
    expect(await api.replaceRootAccess(body)).toEqual(policy);
    expect(request.mock.calls.at(-1)?.[1]).toMatchObject({ method: 'PUT', body: JSON.stringify(body) });
    await expect(api.replaceRootAccess({ ...body, groups: [{ group_id: '', permissions: [] }] })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).toHaveBeenCalledTimes(2);
    request.mockImplementation(async (): Promise<Response> => new Response(JSON.stringify({ ...policy, issuer: 'forbidden' })));
    await expect(api.getRootAccess()).rejects.toBeInstanceOf(SchemaValidationError);
    await expect(api.replaceRootAccess(body)).rejects.toMatchObject({ direction: 'inbound' });
  });
  it('rejects legacy request fields before sending', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>();
    const api = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    const body = { expected_revision: '', groups: [{ ...grant, issuer: 'forbidden' }] };
    await expect(api.replaceRootAccess(body)).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });
  it.each([[409, 'filesystem_policy_stale'], [409, 'filesystem_policy_conflict'], [500, 'filesystem_policy_storage_failure'], [503, 'filesystem_policy_unavailable']] as const)('preserves sanitized HTTP %s errors', async (status, code): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockImplementation(async (): Promise<Response> => new Response(JSON.stringify({ detail: { code } }), { status }));
    const api = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    await expect(api.getRootAccess()).rejects.toMatchObject({ status, body: { detail: { code } } });
    try { await api.getRootAccess(); } catch (error) {
      if (code === 'filesystem_policy_unavailable') expect(policyErrorMessage(error)).toContain('complete authentication setup');
    }
  });
});
