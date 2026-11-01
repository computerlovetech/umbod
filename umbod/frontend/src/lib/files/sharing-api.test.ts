import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryNodeSharing } from './infrastructure/in-memory-sharing.test-support';
import { fileId } from './fixtures.test-support';
import { nodeAccessSchema, replaceAccessSchema, type NodeAccess, type ReplaceAccess, type SharingRecipientType } from './domain/sharing';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
const view: NodeAccess = { node_id: fileId, revision: 'opaque-abc123', grants: [{ recipient: { type: 'group', group_id: ' Team A ', label: 'Team A' }, permissions: ['discover', 'share'] }], blocked_recipients: [{ type: 'group', group_id: 'blocked' }] };

describe('node sharing adapters', (): void => {
  test('in-memory default denies; configured access preserves exact IDs and revisions', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    await expect(sharing.inspectAccess(fileId)).rejects.toMatchObject({ status: 403 });
    sharing.configure(view, [{ group_id: ' Team A ', label: 'Team A', description: 'Description' }, { group_id: 'blocked', label: 'Blocked', description: '' }]);
    expect(await sharing.listEligibleSharingGroups(fileId)).toEqual([{ group_id: ' Team A ', label: 'Team A', description: 'Description' }]);
    await expect(sharing.replaceAccess(fileId, 'stale', { grants: [] }, 'group')).rejects.toMatchObject({ status: 412 });
    await expect(sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'group', group_id: 'unknown' }, permissions: ['read'] }] }, 'group')).rejects.toMatchObject({ status: 422 });
    expect(await sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'group')).toMatchObject({ grants: [], blocked_recipients: [{ type: 'group', group_id: 'blocked' }] });
  });

  test('mixed policy reads filter recipients without changing the global revision and group replacement preserves users', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    const user = { recipient: { type: 'user' as const, user_id: 'user-a', label: 'Person A' }, permissions: ['read' as const] };
    const blockedUser = { type: 'user' as const, user_id: 'protected-user' };
    const mixed = { ...view, grants: [...view.grants, user], blocked_recipients: [...view.blocked_recipients, blockedUser] };
    sharing.configure(mixed, [{ group_id: ' Team A ', label: 'Team A', description: '' }]);
    expect(await sharing.inspectAccess(fileId)).toEqual(mixed);
    expect(await sharing.inspectAccess(fileId, 'group')).toEqual(view);
    expect(await sharing.inspectAccess(fileId, 'user')).toEqual({ ...view, grants: [user], blocked_recipients: [blockedUser] });
    const saved = await sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'group');
    expect(saved).toEqual({ ...view, revision: view.revision + '-next', grants: [] });
    expect(await sharing.inspectAccess(fileId, 'user')).toEqual({ ...saved, grants: [user], blocked_recipients: [blockedUser] });
    expect(await sharing.inspectAccess(fileId)).toEqual({ ...mixed, revision: saved.revision, grants: [user] });
    await expect(sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'user')).rejects.toMatchObject({ status: 412 });
    const userSaved = await sharing.replaceAccess(fileId, saved.revision, { grants: [] }, 'user');
    expect((await sharing.inspectAccess(fileId, 'group')).revision).toBe(userSaved.revision);
  });

  test.each([undefined, 'group', 'user'] as const)('HTTP serializes the optional %s read filter', async (recipientType): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(view));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await api.sharing.inspectAccess(fileId, recipientType);
    expect(fetch.mock.calls[0][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access' + (recipientType ? '?recipient_type=' + recipientType : ''));
  });

  test('HTTP writes user targets without labels and rejects invalid or missing scope before transport', async (): Promise<void> => {
    const result: NodeAccess = { ...view, grants: [{ recipient: { type: 'user', user_id: 'user-a', label: 'Person A' }, permissions: ['read'] }], blocked_recipients: [] };
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(result));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    for (const invalid of [undefined, '', 'other', 'group&recipient_type=user']) {
      expect(() => api.sharing.replaceAccess(fileId, view.revision, { grants: [] }, invalid as SharingRecipientType)).toThrow(SchemaValidationError);
      if (invalid !== undefined) expect(() => api.sharing.inspectAccess(fileId, invalid as SharingRecipientType)).toThrow(SchemaValidationError);
    }
    const body: ReplaceAccess = { grants: [{ recipient: { type: 'user', user_id: 'user-a' }, permissions: ['read'] }] };
    await expect(api.sharing.replaceAccess(fileId, view.revision, body, 'group')).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
    expect(await api.sharing.replaceAccess(fileId, view.revision, body, 'user')).toEqual(result);
    expect(fetch.mock.calls[0]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access?recipient_type=user', expect.objectContaining({ redirect: 'error', body: JSON.stringify(body) })]);
  });

  test.each([
    { groups: [] },
    { grants: [{ recipient: { type: 'group', group_id: 'a', label: 'No outbound labels' }, permissions: ['read'] }] },
    { grants: [{ recipient: { type: 'user', group_id: 'a' }, permissions: ['read'] }] },
    { grants: [{ recipient: { type: 'user', user_id: 'a', group_id: 'b' }, permissions: ['read'] }] },
    { grants: [{ recipient: { type: 'user', user_id: '' }, permissions: ['read'] }] },
    { grants: [{ recipient: { type: 'user', user_id: 'a' }, permissions: [] }] },
    { grants: [{ recipient: { type: 'user', user_id: 'a' }, permissions: ['read', 'read'] }] },
    { grants: Array.from({ length: 2 }, () => ({ recipient: { type: 'user', user_id: 'a' }, permissions: ['read'] })) }
  ])('rejects malformed outbound grants %j', (body): void => {
    expect(replaceAccessSchema.safeParse(body).success).toBe(false);
  });

  test.each([
    { ...view, groups: [] },
    { ...view, grants: [{ recipient: { type: 'user', user_id: 'a' }, permissions: ['read'] }] },
    { ...view, grants: [{ recipient: { type: 'user', user_id: 'a', label: 'A', group_id: 'b' }, permissions: ['read'] }] },
    { ...view, blocked_recipients: [{ type: 'group', group_id: 'a', label: 'Forbidden' }] },
    { ...view, blocked_recipients: [{ type: 'user', user_id: 'a', permissions: ['read'] }] },
    { ...view, blocked_recipients: [{ type: 'unknown', user_id: 'a' }] }
  ])('rejects legacy or malformed inbound views %j', (body): void => {
    expect(nodeAccessSchema.safeParse(body).success).toBe(false);
  });

  test('HTTP sends only groups with strong opaque conditional JSON and reads the node-scoped catalogue', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValueOnce(Response.json(view)).mockResolvedValueOnce(Response.json({ groups: [{ group_id: ' Team A ', label: 'Friendly', description: 'Exact provider group' }] })).mockResolvedValueOnce(Response.json({ ...view, revision: 'new-hash' }));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const signal = new AbortController().signal;
    expect(await api.sharing.inspectAccess(fileId, 'group', signal)).toEqual(view);
    expect(await api.sharing.listEligibleSharingGroups(fileId, signal)).toEqual([{ group_id: ' Team A ', label: 'Friendly', description: 'Exact provider group' }]);
    expect(await api.sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'group', group_id: ' Team A ' }, permissions: ['discover', 'share'] }] }, 'group')).toMatchObject({ revision: 'new-hash' });
    expect(fetch.mock.calls[0]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access?recipient_type=group', expect.objectContaining({ signal })]);
    expect(fetch.mock.calls[1][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access/eligible-groups');
    expect(fetch.mock.calls[2][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access?recipient_type=group');
    expect(fetch.mock.calls[2][1]).toMatchObject({ redirect: 'error', method: 'PUT', headers: { 'If-Match': '"opaque-abc123"', 'content-type': 'application/json' }, body: JSON.stringify({ grants: [{ recipient: { type: 'group', group_id: ' Team A ' }, permissions: ['discover', 'share'] }] }) });
  });

  test.each(['*', 'W/"opaque"', '"one", "two"', '"bad\r\nvalue"', '"bad\u0000value"', '"bad\u007fvalue"', '""', 'unquoted', '"unterminated'])('blocks malformed If-Match %j before any fetch for JSON and absent bodies', async (tag): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const transport = browserTransport({ fetch, configuration });
    for (const body of [undefined, { grants: [] }]) {
      await expect(transport.request({ method: 'PUT', path: '/me/filesystem/nodes/' + fileId + '/access', body, inputSchema: replaceAccessSchema, conditionalHeaders: { 'If-Match': tag } })).rejects.toMatchObject({ direction: 'outbound' });
    }
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each(['raw', 'multipart'] as const)('validates and forwards conditional headers consistently for %s bodies', async (kind): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    const transport = browserTransport({ fetch, configuration });
    const file = new File(['data'], 'payload.txt');
    const requestBody = kind === 'raw'
      ? { kind: 'raw' as const, value: file, schema: z.instanceof(File), headers: { 'content-type': 'text/plain' } }
      : { kind: 'multipart' as const, form: new FormData(), metadata: {}, metadataSchema: z.strictObject({}) };
    await expect(transport.request({ method: 'PUT', path: '/resource', requestBody, conditionalHeaders: { 'If-Match': 'W/"bad"' } })).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
    await transport.request({ method: 'PUT', path: '/resource', requestBody, conditionalHeaders: { 'If-Match': '"opaque-revision"' } });
    expect(fetch.mock.calls[0][1]?.headers).toMatchObject({ 'If-Match': '"opaque-revision"' });
  });

  test('strictly rejects extra replacement fields and malformed authoritative output', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ ...view, revision: 123 }));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await expect(api.sharing.replaceAccess(fileId, view.revision, { grants: [], revision: 'in-body' } as unknown as { grants: [] }, 'group')).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
    await expect(api.sharing.inspectAccess(fileId)).rejects.toMatchObject({ direction: 'inbound' });
  });
});
