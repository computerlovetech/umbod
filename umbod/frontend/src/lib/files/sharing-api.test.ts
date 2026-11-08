import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryNodeSharing } from './infrastructure/in-memory-sharing.test-support';
import { fileId } from './fixtures.test-support';
import { nodeAccessSchema, nodeAccessWriteSchema, replaceAccessSchema, type NodeAccessWrite, type NodeAccess, type ReplaceAccess, type SharingRecipientType, type SharingRecipient } from './domain/sharing';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
const view: NodeAccess = { node_id: fileId, revision: 'opaque-abc123', grants: [{ recipient: { type: 'group', group_id: ' Team A ', label: 'Team A' }, permissions: ['discover', 'share'] }], blocked_recipients: [{ type: 'group', group_id: 'blocked' }] };

describe('node sharing adapters', (): void => {
  test('in-memory default denies; configured access preserves exact IDs and revisions', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    await expect(sharing.inspectAccess(fileId)).rejects.toMatchObject({ status: 403 });
    sharing.configure(view, [{ type: 'group', group_id: ' Team A ', label: 'Team A' }, { type: 'group', group_id: 'blocked', label: 'Blocked' }]);
    expect(await sharing.searchRecipients(fileId, 'team')).toEqual({ recipients: [{ type: 'group', group_id: ' Team A ', label: 'Team A' }], has_more: false });
    await expect(sharing.replaceAccess(fileId, 'stale', { grants: [] }, 'group')).rejects.toMatchObject({ status: 412 });
    await expect(sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'group', group_id: 'unknown' }, permissions: ['read'] }] }, 'group')).rejects.toMatchObject({ status: 422 });
    expect(await sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'group')).toMatchObject({ grants: [], blocked_recipients: [{ type: 'group', group_id: 'blocked' }] });
  });

  test('mixed policy reads filter recipients without changing the global revision and group replacement preserves users', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    const user = { recipient: { type: 'user' as const, user_id: 'user-a', label: 'Person A' }, permissions: ['read' as const] };
    const blockedUser = { type: 'user' as const, user_id: 'protected-user' };
    const mixed = { ...view, grants: [...view.grants, user], blocked_recipients: [...view.blocked_recipients, blockedUser] };
    sharing.configure(mixed, [{ type: 'group', group_id: ' Team A ', label: 'Team A' }, user.recipient]);
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

  test('in-memory search normalizes whitespace and case, excludes blocked targets, and never searches user IDs', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    const recipients: SharingRecipient[] = [
      { type: 'group', group_id: 'Match\t Group', label: 'Other label' },
      { type: 'group', group_id: 'literal', label: 'Match  Group [a.*]' },
      { type: 'user', user_id: 'private-id', label: 'Match\nGroup' },
      { type: 'user', user_id: 'match group', label: 'Other person' },
      { type: 'group', group_id: 'blocked', label: 'Match group' },
      { type: 'user', user_id: 'blocked-user', label: 'Match group' }
    ];
    sharing.configure({ ...view, blocked_recipients: [...view.blocked_recipients, { type: 'user', user_id: 'blocked-user' }] }, recipients);
    expect(await sharing.searchRecipients(fileId, '  mAtCh \t group  ')).toEqual({ recipients: recipients.slice(0, 3), has_more: false });
    expect(await sharing.searchRecipients(fileId, 'match group', 'group')).toEqual({ recipients: recipients.slice(0, 2), has_more: false });
    expect(await sharing.searchRecipients(fileId, 'match group', 'user')).toEqual({ recipients: [recipients[2]], has_more: false });
    expect(await sharing.searchRecipients(fileId, '[a.*]')).toEqual({ recipients: [recipients[1]], has_more: false });
    expect(await sharing.searchRecipients(fileId, 'private-id')).toEqual({ recipients: [], has_more: false });
    const controller = new AbortController();
    controller.abort();
    await expect(sharing.searchRecipients(fileId, 'match', undefined, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    sharing.revoke(fileId);
    await expect(sharing.searchRecipients(fileId, 'match')).rejects.toMatchObject({ status: 403 });
  });

  test.each([50, 51])('in-memory search returns at most fifty of %s matches with an accurate continuation flag', async (count): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    const recipients: SharingRecipient[] = Array.from({ length: count }, (_, index) => ({ type: 'user', user_id: String(index), label: 'Person ' + index }));
    sharing.configure(view, recipients);
    expect(await sharing.searchRecipients(fileId, 'person')).toEqual({ recipients: recipients.slice(0, 50), has_more: count > 50 });
  });

  test('in-memory scoped user save rejects unknown and blocked users and preserves group grants', async (): Promise<void> => {
    const sharing = new InMemoryNodeSharing();
    const user: SharingRecipient = { type: 'user', user_id: 'user-a', label: 'Person A' };
    const blocked: SharingRecipient = { type: 'user', user_id: 'protected', label: 'Protected' };
    sharing.configure({ ...view, blocked_recipients: [...view.blocked_recipients, { type: 'user', user_id: blocked.user_id }] }, [view.grants[0].recipient, user, blocked]);
    for (const user_id of ['unknown', blocked.user_id]) {
      await expect(sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'user', user_id }, permissions: ['read'] }] }, 'user')).rejects.toMatchObject({ status: 422 });
    }
    const saved = await sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'user', user_id: user.user_id }, permissions: ['read'] }] }, 'user');
    expect(saved.grants).toEqual([{ recipient: user, permissions: ['read'] }]);
    expect((await sharing.inspectAccess(fileId, 'group')).grants).toEqual(view.grants);
  });

  test.each([undefined, 'group', 'user'] as const)('HTTP serializes the optional %s recipient search filter and forwards cancellation', async (recipientType): Promise<void> => {
    const result = { recipients: [{ type: 'user', user_id: 'person', label: 'Person' }], has_more: true };
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(result));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const signal = new AbortController().signal;
    expect(await api.sharing.searchRecipients(fileId, '  A & B?  ', recipientType, signal)).toEqual(result);
    expect(fetch.mock.calls[0]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access/recipients?query=A+%26+B%3F' + (recipientType ? '&recipient_type=' + recipientType : ''), expect.objectContaining({ signal })]);
  });

  test.each(['', ' \t\n ', 'a'.repeat(201)])('search rejects invalid query %j before transport in both adapters', async (query): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const sharing = new InMemoryNodeSharing();
    expect(() => api.sharing.searchRecipients(fileId, query)).toThrow(SchemaValidationError);
    await expect(sharing.searchRecipients(fileId, query)).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each(['', 'other', 'group&recipient_type=user'])('search rejects invalid type filter %j before transport in both adapters', async (recipientType): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const sharing = new InMemoryNodeSharing();
    expect(() => api.sharing.searchRecipients(fileId, 'valid', recipientType as SharingRecipientType)).toThrow(SchemaValidationError);
    await expect(sharing.searchRecipients(fileId, 'valid', recipientType as SharingRecipientType)).rejects.toMatchObject({ direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each([
    { groups: [] },
    { recipients: [] },
    { recipients: [], has_more: 'false' },
    { recipients: [], has_more: false, unexpected: true },
    { recipients: [{ type: 'user', user_id: 'user-a' }], has_more: false },
    { recipients: [{ type: 'group', group_id: 'a', label: 'A', description: '' }], has_more: false },
    { recipients: [{ type: 'user', user_id: 'a', group_id: 'b', label: 'A' }], has_more: false }
  ])('HTTP rejects malformed search results %j', async (response): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(response));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await expect(api.sharing.searchRecipients(fileId, 'valid')).rejects.toMatchObject({ direction: 'inbound' });
  });

  test.each([undefined, 'group', 'user'] as const)('HTTP serializes the optional %s read filter', async (recipientType): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(view));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await api.sharing.inspectAccess(fileId, recipientType);
    expect(fetch.mock.calls[0][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access' + (recipientType ? '?recipient_type=' + recipientType : ''));
  });

  test('HTTP writes user targets without labels and rejects invalid or missing scope before transport', async (): Promise<void> => {
    const result: NodeAccess = { ...view, grants: [{ recipient: { type: 'user', user_id: 'user-a', label: 'Person A' }, permissions: ['read'] }], blocked_recipients: [] };
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json({ ...result, visible_to: { type: 'unavailable' } }));
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

  test('HTTP sends only groups with strong opaque conditional JSON and searches the node-scoped catalogue', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValueOnce(Response.json(view)).mockResolvedValueOnce(Response.json({ recipients: [{ type: 'group', group_id: ' Team A ', label: 'Friendly' }], has_more: false })).mockResolvedValueOnce(Response.json({ ...view, revision: 'new-hash', visible_to: { type: 'unavailable' } }));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    const signal = new AbortController().signal;
    expect(await api.sharing.inspectAccess(fileId, 'group', signal)).toEqual(view);
    expect(await api.sharing.searchRecipients(fileId, ' Team ', 'group', signal)).toEqual({ recipients: [{ type: 'group', group_id: ' Team A ', label: 'Friendly' }], has_more: false });
    expect(await api.sharing.replaceAccess(fileId, view.revision, { grants: [{ recipient: { type: 'group', group_id: ' Team A ' }, permissions: ['discover', 'share'] }] }, 'group')).toMatchObject({ revision: 'new-hash' });
    expect(fetch.mock.calls[0]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access?recipient_type=group', expect.objectContaining({ signal })]);
    expect(fetch.mock.calls[1]).toEqual(['/api/me/filesystem/nodes/' + fileId + '/access/recipients?query=Team&recipient_type=group', expect.objectContaining({ signal })]);
    expect(fetch.mock.calls[2][0]).toBe('/api/me/filesystem/nodes/' + fileId + '/access?recipient_type=group');
    expect(fetch.mock.calls[2][1]).toMatchObject({ redirect: 'error', method: 'PUT', headers: { 'If-Match': '"opaque-abc123"', 'content-type': 'application/json' }, body: JSON.stringify({ grants: [{ recipient: { type: 'group', group_id: ' Team A ' }, permissions: ['discover', 'share'] }] }) });
  });

  test.each([
    { type: 'restricted' },
    { type: 'unavailable' },
    { type: 'available', scope: 'direct_node_policy', owner: { type: 'user', issuer: 'https://identity.test', id: 'owner' }, grants: [], group_members_expanded: false }
  ] satisfies NodeAccessWrite['visible_to'][])('validates write visibility without changing the read port contract %j', async (visible_to): Promise<void> => {
    const response = { ...view, visible_to };
    expect(nodeAccessWriteSchema.parse(response)).toEqual(response);
    expect(nodeAccessSchema.safeParse(response).success).toBe(false);
    const fetch = vi.fn<typeof globalThis.fetch>().mockImplementation(async (): Promise<Response> => Response.json(response));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    expect(await api.sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'group')).toEqual(view);
    await expect(api.sharing.inspectAccess(fileId)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test.each([
    view,
    { ...view, visible_to: null },
    { ...view, visible_to: { type: 'unknown' } },
    { ...view, visible_to: { type: 'restricted', grants: [] } },
    { ...view, visible_to: { type: 'available', scope: 'direct_node_policy', owner: { type: 'user', issuer: 'issuer', id: 'owner' }, grants: [], group_members_expanded: true } },
    { ...view, visible_to: { type: 'unavailable' }, unexpected: true }
  ])('rejects missing or malformed write visibility and unknown fields %j', async (response): Promise<void> => {
    expect(nodeAccessWriteSchema.safeParse(response).success).toBe(false);
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValue(Response.json(response));
    const api = new FilesApi(browserTransport({ fetch, configuration }));
    await expect(api.sharing.replaceAccess(fileId, view.revision, { grants: [] }, 'group')).rejects.toMatchObject({ direction: 'inbound' });
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
