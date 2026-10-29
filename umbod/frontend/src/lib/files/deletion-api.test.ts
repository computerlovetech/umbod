import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, browserTransport, HttpError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryFilesApi } from './infrastructure/in-memory-api';
import { fileId, filesystemFixture, folderId, rootId } from './fixtures.test-support';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });

function httpApi(fetch: typeof globalThis.fetch): FilesApi {
  return new FilesApi(browserTransport({ fetch, configuration }));
}

describe('file deletion port', (): void => {
  test('checks without mutation, enforces revision and deletes only the file', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    await api.filesystem.checkDeleteEligibility(fileId);
    expect(await api.filesystem.getNode(fileId)).toEqual(filesystemFixture[2]);
    await expect(api.filesystem.deleteFile(fileId, 2)).rejects.toMatchObject({ status: 412 });
    await api.filesystem.deleteFile(fileId, 1);
    expect(await api.filesystem.listChildren(folderId)).toEqual([]);
    await expect(api.filesystem.deleteFile(fileId, 1)).rejects.toMatchObject({ status: 403 });
    await expect(api.filesystem.checkDeleteEligibility(fileId)).rejects.toMatchObject({ status: 403 });
  });

  test('completion after deletion denies without recreating the file or removing session history', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const session = await api.filesystem.beginUpload(folderId, {
      name: 'Uploaded.txt', metadata: { content_type: 'text/plain', attributes: {} }, size_bytes: 5
    });
    await api.filesystem.transferUpload(session, new File(['hello'], 'Uploaded.txt'));
    const node = await api.filesystem.completeUpload(session);
    await api.filesystem.deleteFile(node.id, node.revision);
    await expect(api.filesystem.completeUpload(session)).rejects.toMatchObject({ status: 403 });
    await expect(api.filesystem.completeUpload(session)).rejects.toMatchObject({ status: 403 });
    expect(await api.filesystem.getUpload(session.id)).toMatchObject({ id: session.id, status: 'completed' });
    expect((await api.filesystem.listChildren(folderId)).map((child) => child.id)).toEqual([fileId]);
    await expect(api.filesystem.getNode(node.id)).rejects.toMatchObject({ status: 404 });
  });

  test.each([rootId, folderId])('never deletes directory %s', async (id): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    await expect(api.filesystem.checkDeleteEligibility(id)).rejects.toMatchObject({ status: 409 });
    await expect(api.filesystem.deleteFile(id, 1)).rejects.toMatchObject({ status: 409 });
  });

  test('rechecks authorization before revealing stale revisions', async (): Promise<void> => {
    let allowed = true;
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, () => allowed);
    await api.filesystem.checkDeleteEligibility(fileId);
    allowed = false;
    await expect(api.filesystem.checkDeleteEligibility(fileId)).rejects.toMatchObject({ status: 403 });
    await expect(api.filesystem.deleteFile(fileId, 2)).rejects.toMatchObject({ status: 403 });
    expect(await api.filesystem.getNode(fileId)).toEqual(filesystemFixture[2]);
  });
});

describe('file deletion HTTP adapter', (): void => {
  test('checks Allow with independent signal and sends quoted revision without a body', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>().mockResolvedValueOnce(new Response(null, { status: 204, headers: { Allow: 'GET, DELETE, OPTIONS' } })).mockResolvedValueOnce(new Response(null, { status: 204 }));
    const api = httpApi(fetch);
    const signal = new AbortController().signal;
    await api.filesystem.checkDeleteEligibility(fileId, signal);
    await api.filesystem.deleteFile(fileId, 7);
    expect(fetch).toHaveBeenNthCalledWith(1, '/api/me/filesystem/nodes/' + fileId, expect.objectContaining({ method: 'OPTIONS', signal }));
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/me/filesystem/nodes/' + fileId, expect.objectContaining({ method: 'DELETE', credentials: 'same-origin', redirect: 'error', headers: expect.objectContaining({ 'If-Match': '"7"' }) }));
    expect(fetch.mock.calls[1][1]?.body).toBeUndefined();
  });

  test.each([undefined, '', 'GET, OPTIONS', 'delete', 'X-DELETE'])('fails closed for Allow %s', async (allow): Promise<void> => {
    const api = httpApi(vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 204, headers: allow === undefined ? {} : { Allow: allow } })));
    await expect(api.filesystem.checkDeleteEligibility(fileId)).rejects.toBeInstanceOf(SchemaValidationError);
  });

  test.each([0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1])('rejects revision %s before HTTP', async (revision): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const api = httpApi(fetch);
    expect(() => api.filesystem.deleteFile(fileId, revision)).toThrow(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
  });

  test.each([403, 409, 412])('preserves authoritative status %s', async (status): Promise<void> => {
    const api = httpApi(vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response('{}', { status })));
    await expect(api.filesystem.deleteFile(fileId, 1)).rejects.toBeInstanceOf(HttpError);
    await expect(api.filesystem.deleteFile(fileId, 1)).rejects.toMatchObject({ status });
  });

  test('conditional headers cannot override authentication or inject arbitrary headers', async (): Promise<void> => {
    const fetch = vi.fn<typeof globalThis.fetch>();
    const transport = browserTransport({ fetch, configuration, bearerToken: () => 'token' });
    await expect(transport.request({
      method: 'DELETE', path: '/me/filesystem/nodes/' + fileId,
      conditionalHeaders: { 'If-Match': '"1"', authorization: 'override' } as { 'If-Match': string }
    })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
    await expect(transport.request({
      method: 'DELETE', path: '/me/filesystem/nodes/' + fileId, conditionalHeaders: { 'If-Match': '*' }
    })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
  });

  test('maps authentication separately', async (): Promise<void> => {
    const api = httpApi(vi.fn<typeof globalThis.fetch>().mockResolvedValue(new Response(null, { status: 401 })));
    await expect(api.filesystem.deleteFile(fileId, 1)).rejects.toBeInstanceOf(AuthenticationRequiredError);
  });
});
