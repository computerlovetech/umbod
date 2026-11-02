import { describe, expect, test, vi } from 'vitest';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryFilesApi } from './infrastructure/in-memory-api.test-support';
import { fileId, filesystemFixture, folderId, rootId } from './fixtures.test-support';
import { updateDescriptionSchema, updateNodeSchema } from './domain/schemas';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });

function http(request: typeof fetch): FilesApi {
  return new FilesApi(browserTransport({ origin: () => 'https://umbod.test', fetch: request, configuration }), () => 'https://umbod.test');
}

describe('description API contract', (): void => {
  test.each([fileId, folderId])('checks and updates %s through node OPTIONS and quoted revision metadata PATCH', async (id): Promise<void> => {
    const returned = { ...filesystemFixture.find((node) => node.id === id)!, revision: 2 };
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 204, headers: { Allow: 'PATCH, OPTIONS' } })).mockResolvedValueOnce(Response.json(returned, { headers: { ETag: '"2"' } }));
    const api = http(request);
    const signal = new AbortController().signal;
    await api.filesystem.checkDescriptionEligibility(id, signal);
    expect(await api.filesystem.updateDescription(id, 1, { description: '' })).toEqual(returned);
    expect(request.mock.calls.map(([path, init]) => [path, init?.method])).toEqual([
      ['/api/me/filesystem/nodes/' + id, 'OPTIONS'],
      ['/api/me/filesystem/nodes/' + id, 'PATCH']
    ]);
    expect(request.mock.calls[0][1]?.signal).toBe(signal);
    expect(new Headers(request.mock.calls[1][1]?.headers).get('If-Match')).toBe('"1"');
    expect(JSON.parse(String(request.mock.calls[1][1]?.body))).toEqual({ metadata: { attributes: { description: '' } } });
  });

  test('validates outgoing descriptions and incoming authority and nodes', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(null, { status: 204, headers: { Allow: 'OPTIONS' } })).mockResolvedValueOnce(Response.json({ invalid: true }));
    const api = http(request);
    expect(updateDescriptionSchema.safeParse({ description: 1 }).success).toBe(false);
    expect(updateDescriptionSchema.parse({ description: 'x'.repeat(100000) }).description).toHaveLength(100000);
    expect(() => api.filesystem.updateDescription(fileId, 0, { description: '' })).toThrow();
    expect(request).not.toHaveBeenCalled();
    await expect(api.filesystem.checkDescriptionEligibility(fileId)).rejects.toMatchObject({ status: 403 });
    await expect(api.filesystem.updateDescription(fileId, 1, { description: 'value' })).rejects.toMatchObject({ direction: 'inbound' });
  });

  test.each(['GET, OPTIONS', 'GET, DELETE, OPTIONS', 'GET, HEAD, OPTIONS', 'GET, X-PATCH, OPTIONS'])('hides description editing when node Allow is %s', async (allow): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204, headers: { Allow: allow } }));
    await expect(http(request).filesystem.checkDescriptionEligibility(fileId)).rejects.toMatchObject({ status: 403 });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([undefined, '', 'patch, OPTIONS', 'PATCH OPTIONS'])('rejects malformed node Allow %s', async (allow): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204, headers: allow === undefined ? {} : { Allow: allow } }));
    await expect(http(request).filesystem.checkDescriptionEligibility(fileId)).rejects.toMatchObject({ direction: 'inbound' });
  });

  test.each([
    {}, { metadata: {} }, { metadata: { attributes: {} } }, { metadata: { attributes: null } },
    { metadata: { content_type: null } }, { metadata: { attributes: { description: 1 } } },
    { name: null }, { parent_id: null }, { metadata: null }, { unknown: 'value' }
  ])('rejects invalid node patches %j', (input): void => {
    expect(updateNodeSchema.safeParse(input).success).toBe(false);
  });

  test.each([
    { metadata: { attributes: { description: '', category: 'release' } } },
    { metadata: { content_type: 'text/plain' } },
    { metadata: { content_type: {} } }
  ])('accepts partial metadata patches %j', (input): void => {
    expect(updateNodeSchema.parse(input)).toEqual(input);
  });

  test.each([403, 412, 500])('preserves PATCH %s without retry', async (status): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({}, { status }));
    await expect(http(request).filesystem.updateDescription(fileId, 1, { description: 'value' })).rejects.toMatchObject({ status });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test('in-memory authority denies discover/write failures and missing nodes, and rejects stale revisions', async (): Promise<void> => {
    for (const [read, write] of [[false, true], [true, false]]) {
      const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, () => read, () => write);
      await expect(api.filesystem.checkDescriptionEligibility(fileId)).rejects.toMatchObject({ status: 403 });
      await expect(api.filesystem.updateDescription(fileId, 1, { description: 'value' })).rejects.toMatchObject({ status: 403 });
    }
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    await expect(api.filesystem.checkDescriptionEligibility(crypto.randomUUID())).rejects.toMatchObject({ status: 403 });
    await api.filesystem.updateDescription(fileId, 1, { description: 'value' });
    await expect(api.filesystem.updateDescription(fileId, 1, { description: '' })).rejects.toMatchObject({ status: 412 });
  });

  test('HTTP upload forwards description in session metadata', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({}, { status: 403 }));
    await expect(http(request).filesystem.uploadFile(rootId, { file: new File([], 'file'), name: 'file', description: 'Read me' })).rejects.toBeDefined();
    expect(JSON.parse(String(request.mock.calls[0][1]?.body)).metadata.attributes).toEqual({ description: 'Read me' });
  });
});
