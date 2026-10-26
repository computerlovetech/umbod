import { describe, expect, it, vi } from 'vitest';
import type { FilesystemAdministration } from './port';
import { InMemoryFilesystemAdministration } from './in-memory';
import { rootPolicy } from './fixtures.test-support';
import { FilesystemRoute } from './http-route';
import { browserTransport, HttpError, SchemaValidationError } from '../infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '../infrastructure/public-configuration';
import { replaceRootAccessSchema } from './domain/schemas';

describe('filesystem administration port', () => {
  it('initializes an empty policy, replaces all grants and rejects a stale revision', async () => {
    const api: FilesystemAdministration = new InMemoryFilesystemAdministration(rootPolicy());
    const empty = await api.replaceRootAccess({ expected_revision: 'initial', groups: [] });
    expect(empty.status).toBe('ready');
    const group = { issuer: ' exact issuer ', group_id: 'Exact Group', permissions: ['discover', 'write'] as const };
    const granted = await api.replaceRootAccess({ expected_revision: empty.revision, groups: [{ ...group, permissions: [...group.permissions] }] });
    expect(granted.groups[0].issuer).toBe(' exact issuer ');
    const revoked = await api.replaceRootAccess({ expected_revision: granted.revision, groups: [] });
    expect(revoked.groups).toEqual([]);
    await expect(api.replaceRootAccess({ expected_revision: 'initial', groups: [] })).rejects.toMatchObject({ status: 409, body: { detail: { code: 'filesystem_policy_stale' } } });
  });
  it.each(['issuer', 'group_id'] as const)('rejects blank %s without silently trimming', (field) => {
    expect(replaceRootAccessSchema.safeParse({ expected_revision: '', groups: [{ issuer: 'issuer', group_id: 'id', permissions: ['read'], [field]: ' ' }] }).success).toBe(false);
  });
  it('rejects duplicate identities, missing permissions and forbidden request fields', () => {
    const grant = { issuer: 'issuer', group_id: 'id', permissions: ['read'] };
    for (const groups of [[grant, grant], [{ ...grant, permissions: [] }]]) expect(replaceRootAccessSchema.safeParse({ expected_revision: '', groups }).success).toBe(false);
    expect(replaceRootAccessSchema.safeParse({ expected_revision: '', groups: [], owner: 'admin' }).success).toBe(false);
  });
  it('rejects legacy conflicts and unmanaged overlaps', async () => {
    const grant = { issuer: 'issuer', group_id: 'id', permissions: ['read'] as const };
    for (const policy of [rootPolicy({ status: 'conflict' }), rootPolicy({ unmanaged_groups: [{ ...grant, permissions: [...grant.permissions] }] })]) {
      const api: FilesystemAdministration = new InMemoryFilesystemAdministration(policy);
      await expect(api.replaceRootAccess({ expected_revision: 'initial', groups: [{ ...grant, permissions: [...grant.permissions] }] })).rejects.toBeInstanceOf(HttpError);
    }
  });
});
describe('filesystem HTTP boundary', () => {
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
  it('loads observed legacy grants without relaxing submitted grants', async () => {
    const legacyGroups = [
      { issuer: 'issuer', group_id: 'empty-permissions', permissions: [] },
      { issuer: '', group_id: 'blank-issuer', permissions: ['read'] as const },
      { issuer: 'issuer', group_id: ' ', permissions: ['read'] as const }
    ].map((group) => ({ ...group, permissions: [...group.permissions] }));
    const policy = rootPolicy({ status: 'ready', groups: legacyGroups, unmanaged_groups: legacyGroups });
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(policy)));
    const api: FilesystemAdministration = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    expect(await api.getRootAccess()).toEqual(policy);
    for (const group of legacyGroups) {
      await expect(api.replaceRootAccess({ expected_revision: policy.revision, groups: [group] })).rejects.toMatchObject({ direction: 'outbound' });
    }
    expect(request).toHaveBeenCalledTimes(1);
  });
  it('wires the route, validates both boundaries and never sends invalid input', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(rootPolicy())));
    const api: FilesystemAdministration = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    expect(await api.getRootAccess()).toEqual(rootPolicy());
    expect(request.mock.calls[0][0]).toBe('/api/admin/filesystem/root-access');
    await expect(api.replaceRootAccess({ expected_revision: '', groups: [{ issuer: '', group_id: '', permissions: [] }] })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).toHaveBeenCalledTimes(1);
    request.mockResolvedValue(new Response('{}'));
    await expect(api.getRootAccess()).rejects.toBeInstanceOf(SchemaValidationError);
    request.mockResolvedValue(new Response(JSON.stringify(rootPolicy({ status: 'ready' }))));
    await api.replaceRootAccess({ expected_revision: 'initial', groups: [] });
    expect(request.mock.calls.at(-1)?.[1]).toMatchObject({ method: 'PUT', body: JSON.stringify({ expected_revision: 'initial', groups: [] }) });
  });
  it.each([[409, 'filesystem_policy_stale'], [409, 'filesystem_policy_conflict'], [500, 'filesystem_policy_storage_failure']] as const)('preserves typed HTTP %s errors', async (status, code) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ detail: { code } }), { status }));
    const api: FilesystemAdministration = new FilesystemRoute(browserTransport({ fetch: request, configuration }));
    await expect(api.getRootAccess()).rejects.toMatchObject({ status, body: { detail: { code } } });
  });
});
