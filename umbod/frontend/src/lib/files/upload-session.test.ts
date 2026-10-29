import { describe, expect, test, vi } from 'vitest';
import { browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { beginUploadSchema, rawUploadSchema, uploadSessionSchema, type UploadSession } from './domain/schemas';
import { FilesApi } from './infrastructure/files-api';
import { InMemoryFilesApi } from './infrastructure/in-memory-api';
import { HttpUploadTransfer } from './infrastructure/upload-transfer';
import { fileId, filesystemFixture, filesystemNode, rootId } from './fixtures.test-support';

const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });
const origin = (): string => 'https://umbod.test';
const selected = { file: new File([], 'empty'), name: 'empty' };

function session(): UploadSession {
  return {
    id: fileId, expires_at: '2026-12-01T00:00:00Z', status: 'pending',
    transfer: { type: 'single', method: 'PUT', url: '/api/me/filesystem/uploads/' + fileId + '/content', headers: { 'Content-Type': 'application/octet-stream' }, authorization: { type: 'same_origin' } },
    complete_url: '/api/me/filesystem/uploads/' + fileId + '/complete'
  };
}

function client(request: typeof fetch, external: typeof fetch = vi.fn<typeof fetch>()): FilesApi {
  return new FilesApi(browserTransport({ origin: () => 'https://umbod.test', fetch: request, configuration, bearerToken: () => 'secret' }), origin, external);
}

describe('upload session contract', () => {
  test('retains exact bytes, hides incomplete nodes and completes idempotently', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const file = new File([new Uint8Array([0, 255, 13, 10])], 'binary');
    const session = await api.filesystem.beginUpload(rootId, { name: 'renamed', metadata: { content_type: 'application/octet-stream', attributes: {} }, size_bytes: file.size });
    expect((await api.filesystem.getUpload(session.id)).status).toBe('pending');
    await expect(api.filesystem.completeUpload(session)).rejects.toMatchObject({ status: 409 });
    await api.filesystem.transferUpload(session, file);
    expect((await api.filesystem.getUpload(session.id)).status).toBe('uploaded');
    expect((await api.filesystem.listChildren(rootId)).map((node) => node.name)).toEqual(['Projects']);
    const node = await api.filesystem.completeUpload(session);
    expect(await api.filesystem.completeUpload(session)).toEqual(node);
    expect((await api.filesystem.getUpload(session.id)).status).toBe('completed');
    expect(await api.filesystem.readContent(node.id)).toEqual(new Uint8Array([0, 255, 13, 10]));
    expect((await api.filesystem.listChildren(rootId)).filter((child) => child.id === node.id)).toHaveLength(1);
  });

  test('completion accepts the first 201 and repeated 200 without a request body', async (): Promise<void> => {
    const node = filesystemNode({ parent_id: rootId, kind: 'file', name: 'empty' });
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(node, { status: 201 }))
      .mockResolvedValueOnce(Response.json(node, { status: 200 }));
    const api = client(request);
    expect(await api.filesystem.completeUpload(session())).toEqual(node);
    expect(await api.filesystem.completeUpload({ ...session(), status: 'completed' })).toEqual(node);
    for (const [url, init] of request.mock.calls) {
      expect(url).toBe(session().complete_url);
      expect(init).toMatchObject({ method: 'POST', redirect: 'error', credentials: 'same-origin' });
      expect(init?.body).toBeUndefined();
      expect(new Headers(init?.headers).get('Content-Type')).toBeNull();
    }
  });

  test.each(['pending', 'uploaded', 'completed'] as const)('inspection accepts %s sessions', async (status): Promise<void> => {
    const value = { ...session(), status };
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(value));
    expect(await client(request).filesystem.getUpload(fileId)).toEqual(value);
    expect(uploadSessionSchema.parse(value).status).toBe(status);
  });

  test.each([-1, 1.5, Infinity, Number.MAX_SAFE_INTEGER + 1])('rejects invalid advertised byte count %s', (size_bytes): void => {
    expect(beginUploadSchema.safeParse({ name: 'file', metadata: { content_type: 'text/plain', attributes: {} }, size_bytes }).success).toBe(false);
  });

  test('empty browser content type uses octet stream and empty raw files are sent', async (): Promise<void> => {
    const node = filesystemNode({ parent_id: rootId, kind: 'file', name: 'empty' });
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(session(), { status: 201 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json(node, { status: 201 }));
    await client(request).filesystem.uploadFile(rootId, selected);
    expect(JSON.parse(String(request.mock.calls[0][1]?.body))).toEqual({ name: 'empty', metadata: { content_type: 'application/octet-stream', attributes: {} }, size_bytes: 0 });
    expect(request.mock.calls[1][1]?.body).toBe(selected.file);
  });

  test.each([
    { transfer: { ...session().transfer, type: 'multipart' } },
    { transfer: { ...session().transfer, method: 'POST' } },
    { transfer: { ...session().transfer, headers: { Authorization: 'secret' } } },
    { transfer: { ...session().transfer, authorization: { type: 'bearer' } } },
    { status: 'unknown' },
    { expires_at: 'tomorrow' }
  ])('rejects invalid session descriptors before transfer or completion: %j', async (override): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ ...session(), ...override }));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toMatchObject({ phase: 'begin', cause: expect.any(SchemaValidationError) });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    'https://attacker.test/api/me/filesystem/uploads/' + fileId + '/complete',
    '/api/me/filesystem/root',
    '/api/me/filesystem/uploads/' + rootId + '/complete',
    session().complete_url + '?redirect=1',
    session().complete_url + '#fragment'
  ])('rejects unsafe completion endpoint before authenticated completion: %s', async (complete_url): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json({ ...session(), complete_url })).mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toThrow('Unsafe API endpoint');
    expect(request).toHaveBeenCalledTimes(2);
  });

  test.each(['https://attacker.test/content', '/api/me/filesystem/root', '/api/me/filesystem/uploads/' + rootId + '/content'])('same-origin authorization cannot target arbitrary content URLs: %s', async (url): Promise<void> => {
    const value = session();
    value.transfer.url = url;
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(value));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toThrow('Unsafe API endpoint');
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([403, 413, 500])('transfer HTTP failure %s never completes', async (status): Promise<void> => {
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(session()))
      .mockResolvedValueOnce(new Response(null, { status }));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toMatchObject({ phase: 'transfer', cause: { status } });
    expect(request).toHaveBeenCalledTimes(2);
  });

  test('redirect rejection at transfer never completes', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(session())).mockRejectedValueOnce(new TypeError('redirect'));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toThrow('could not be reached');
    expect(request.mock.calls[1][1]?.redirect).toBe('error');
    expect(request).toHaveBeenCalledTimes(2);
  });

  test('raw transport validates the File before invoking fetch', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>();
    const transport = browserTransport({ origin: () => 'https://umbod.test', fetch: request, configuration });
    await expect(transport.request({ method: 'PUT', path: '/content', requestBody: { kind: 'raw', value: new Blob([]) as File, schema: rawUploadSchema, headers: {} } })).rejects.toMatchObject({ direction: 'outbound' });
    expect(request).not.toHaveBeenCalled();
  });
});

describe('upload instruction headers and configured bases', () => {
  test.each(['same_origin', 'none'] as const)('preserves receiver checksum headers with %s authorization', async (authorization): Promise<void> => {
    const value = session();
    value.transfer.authorization = { type: authorization };
    value.transfer.headers['x-amz-checksum-sha256'] = 'opaque-checksum=';
    if (authorization === 'none') value.transfer.url = 'https://storage.test/signed';
    const node = filesystemNode({ parent_id: rootId, kind: 'file', name: 'empty' });
    const authenticated = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(value));
    const external = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    if (authorization === 'same_origin') authenticated.mockResolvedValueOnce(new Response(null, { status: 204 }));
    authenticated.mockResolvedValueOnce(Response.json(node));
    await client(authenticated, external).filesystem.uploadFile(rootId, selected);
    const init = authorization === 'same_origin' ? authenticated.mock.calls[1][1] : external.mock.calls[0][1];
    expect(new Headers(init?.headers).get('x-amz-checksum-sha256')).toBe('opaque-checksum=');
    if (authorization === 'none') {
      expect(init?.credentials).toBe('omit');
      expect(new Headers(init?.headers).get('authorization')).toBeNull();
      expect(new Headers(init?.headers).get('X-Umbod-Web-Request')).toBeNull();
    }
  });

  test.each(['AUTHORIZATION', 'Cookie', 'x-UMbod-web-request', 'Proxy-Authorization', 'X-CSRF-Token', 'Origin'])('rejects same-origin credential override %s before PUT', async (header): Promise<void> => {
    const value = session();
    value.transfer.headers[header] = 'attacker-value';
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(value));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toMatchObject({ phase: 'transfer', message: expect.stringContaining('cannot override') });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    { 'bad header': 'value', 'Content-Type': 'text/plain' },
    { 'X-Checksum': 'bad\r\nAuthorization: secret', 'Content-Type': 'text/plain' },
    { 'X-Checksum': 'bad\nvalue', 'Content-Type': 'text/plain' }
  ])('rejects invalid header instructions %j before transfer', async (headers): Promise<void> => {
    const value = { ...session(), transfer: { ...session().transfer, headers } };
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(value));
    await expect(client(request).filesystem.uploadFile(rootId, selected)).rejects.toMatchObject({ phase: 'begin', cause: expect.any(SchemaValidationError) });
    expect(request).toHaveBeenCalledTimes(1);
  });

  test.each([
    { apiBaseUrl: '/api', prefix: '/api', expectedBase: '/api' },
    { apiBaseUrl: '/gateway/api', prefix: '/gateway/api', expectedBase: '/gateway/api' },
    { apiBaseUrl: 'https://backend.test/api', prefix: '/api', expectedBase: 'https://backend.test/api' }
  ])('resolves session requests against trusted configured base $apiBaseUrl', async ({ apiBaseUrl, prefix, expectedBase }): Promise<void> => {
    const configured = new InMemoryPublicConfigurationProvider({ apiBaseUrl, mcpBaseUrl: '/mcp' });
    const value = session();
    value.transfer.url = prefix + '/me/filesystem/uploads/' + fileId + '/content';
    value.complete_url = prefix + '/me/filesystem/uploads/' + fileId + '/complete';
    const request = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(Response.json(value))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(Response.json(filesystemNode({ parent_id: rootId, kind: 'file', name: 'empty' })));
    const api = new FilesApi(browserTransport({ origin, fetch: request, configuration: configured }), origin);
    await api.filesystem.uploadFile(rootId, selected);
    expect(request.mock.calls.map(([url]) => url)).toEqual([
      apiBaseUrl + '/me/filesystem/nodes/' + rootId + '/uploads',
      expectedBase + '/me/filesystem/uploads/' + fileId + '/content',
      expectedBase + '/me/filesystem/uploads/' + fileId + '/complete'
    ]);
  });

  test.each(['content', 'complete'] as const)('accepts absolute trusted API %s URL but rejects frontend and untrusted origins', async (operation): Promise<void> => {
    const configured = new InMemoryPublicConfigurationProvider({ apiBaseUrl: 'https://backend.test/api', mcpBaseUrl: '/mcp' });
    for (const targetOrigin of ['https://backend.test', 'https://umbod.test', 'https://attacker.test']) {
      const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
      const transport = browserTransport({ origin, fetch: request, configuration: configured, bearerToken: () => 'secret' });
      const result = transport.request({
        method: operation === 'content' ? 'PUT' : 'POST',
        path: targetOrigin + '/api/me/filesystem/uploads/' + fileId + '/' + operation,
        apiEndpoint: { method: operation === 'content' ? 'PUT' : 'POST', path: `/me/filesystem/uploads/${fileId}/${operation}` }, redirect: 'error'
      });
      if (targetOrigin === 'https://backend.test') {
        await expect(result).resolves.toBeUndefined();
        expect(request.mock.calls[0][0]).toBe(targetOrigin + '/api/me/filesystem/uploads/' + fileId + '/' + operation);
      } else {
        await expect(result).rejects.toThrow('Unsafe API endpoint');
        expect(request).not.toHaveBeenCalled();
      }
    }
  });

  test.each(['/api/me/filesystem/uploads/' + fileId + '/content', '/gateway/api/me/filesystem/uploads/' + rootId + '/content'])('rejects wrong API prefix or session ID under a configured prefix: %s', async (path): Promise<void> => {
    const configured = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/gateway/api', mcpBaseUrl: '/mcp' });
    const request = vi.fn<typeof fetch>();
    const transport = browserTransport({ origin, fetch: request, configuration: configured });
    await expect(transport.request({ method: 'PUT', path, apiEndpoint: { method: 'PUT', path: `/me/filesystem/uploads/${fileId}/content` } })).rejects.toThrow('Unsafe API endpoint');
    expect(request).not.toHaveBeenCalled();
  });
});

describe('credential-isolated external transfer', () => {
  test('none uses separate fetch without cookies, Umbod auth, referrers or redirects', async (): Promise<void> => {
    const value = session();
    value.transfer.authorization = { type: 'none' };
    value.transfer.url = 'https://storage.test/signed?signature=opaque';
    const node = filesystemNode({ parent_id: rootId, kind: 'file', name: 'empty' });
    const authenticated = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json(value)).mockResolvedValueOnce(Response.json(node));
    const external = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    await client(authenticated, external).filesystem.uploadFile(rootId, selected);
    expect(authenticated).toHaveBeenCalledTimes(2);
    expect(external).toHaveBeenCalledExactlyOnceWith(value.transfer.url, {
      method: 'PUT', body: selected.file, headers: { 'Content-Type': 'application/octet-stream' }, credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer'
    });
  });

  test('external redirect failure does not complete or use authenticated transport', async (): Promise<void> => {
    const value = session();
    value.transfer.authorization = { type: 'none' };
    value.transfer.url = 'https://storage.test/signed';
    const authenticated = vi.fn<typeof fetch>().mockResolvedValue(Response.json(value));
    const external = vi.fn<typeof fetch>().mockRejectedValue(new TypeError('redirect'));
    await expect(client(authenticated, external).filesystem.uploadFile(rootId, selected)).rejects.toThrow('could not be reached');
    expect(authenticated).toHaveBeenCalledTimes(1);
    expect(external.mock.calls[0][1]?.redirect).toBe('error');
  });

  test('validates descriptor and body even when called directly through the transfer port', async (): Promise<void> => {
    const authenticated = vi.fn<typeof fetch>();
    const external = vi.fn<typeof fetch>();
    const transfer = new HttpUploadTransfer(browserTransport({ origin: () => 'https://umbod.test', fetch: authenticated, configuration }), origin, external);
    await expect(transfer.transfer({ ...session().transfer, type: 'chunked' } as unknown as UploadSession['transfer'], selected.file, fileId)).rejects.toMatchObject({ direction: 'inbound' });
    await expect(transfer.transfer(session().transfer, new Blob([]) as File, fileId)).rejects.toMatchObject({ direction: 'outbound' });
    expect(authenticated).not.toHaveBeenCalled();
    expect(external).not.toHaveBeenCalled();
  });
});
