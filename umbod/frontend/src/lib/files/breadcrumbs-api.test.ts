import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, browserTransport, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { breadcrumbsSchema, type Breadcrumbs } from './domain/schemas';
import { fileId, filesystemFixture, filesystemNode, folderId, rootId } from './fixtures.test-support';
import { InMemoryFilesApi } from './infrastructure/in-memory-api.test-support';
import { FilesApi } from './infrastructure/files-api';

const complete: Breadcrumbs = { items: filesystemFixture.map(({ id, name, kind }) => ({ id, name, kind })), complete: true };
const missingId = '00000000-0000-4000-8000-000000000099';
const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' });

function http(request: typeof fetch): FilesApi {
  return new FilesApi(browserTransport({ origin: () => 'https://umbod.test', fetch: request, configuration }), () => 'https://umbod.test');
}

describe('breadcrumb port', () => {
  test('returns minimal ordered target-inclusive paths including empty root names', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture).filesystem;
    expect(await api.getBreadcrumbs(fileId)).toEqual(complete);
    expect(await api.getBreadcrumbs(rootId)).toEqual({ items: [complete.items[0]], complete: true });
    expect(await api.getBreadcrumbs(folderId)).toEqual({ items: complete.items.slice(0, 2), complete: true });
  });

  test('stops at the first inaccessible ancestor without leaking fields or jumping to a visible root', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== folderId).filesystem;
    expect(await api.getBreadcrumbs(fileId)).toEqual({ items: [complete.items[2]], complete: false });
    expect(await api.listChildren(rootId)).toEqual([]);
    await expect(api.getBreadcrumbs(folderId)).rejects.toMatchObject({ status: 403 });
    await expect(api.getBreadcrumbs(missingId)).rejects.toMatchObject({ status: 403 });
  });

  test('retains the contiguous visible suffix and honors visibility changes', async (): Promise<void> => {
    let rootVisible = false;
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== rootId || rootVisible).filesystem;
    expect(await api.getBreadcrumbs(fileId)).toEqual({ items: complete.items.slice(1), complete: false });
    rootVisible = true;
    expect(await api.getBreadcrumbs(fileId)).toEqual(complete);
  });

  test('missing ancestry yields only the visible suffix', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, [filesystemFixture[0], filesystemNode({ ...filesystemFixture[2], parent_id: missingId })]).filesystem;
    expect(await api.getBreadcrumbs(fileId)).toEqual({ items: [complete.items[2]], complete: false });
  });

  test('cycles fail generically without returning diagnostic node fields', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, [filesystemFixture[0], { ...filesystemFixture[1], parent_id: folderId }, filesystemFixture[2]]).filesystem;
    await expect(api.getBreadcrumbs(fileId)).rejects.toThrow('Unable to load path');
    const controller = new AbortController();
    controller.abort();
    await expect(api.getBreadcrumbs(fileId, controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
  });
});

describe('strict breadcrumb schemas', () => {
  test.each([
    { items: [], complete: true },
    { items: complete.items },
    { ...complete, complete: 'true' },
    { ...complete, hidden: rootId },
    { items: [{ ...complete.items[0], parent_id: folderId }], complete: false },
    { items: [{ ...complete.items[0], id: 'invalid' }], complete: false },
    { items: [{ ...complete.items[0], kind: 'link' }], complete: false },
    { items: [{ ...complete.items[0], name: null }], complete: false }
  ])('rejects malformed or nonminimal data %j', (body): void => {
    expect(breadcrumbsSchema.safeParse(body).success).toBe(false);
  });
});

describe('breadcrumb HTTP adapter', () => {
  test('uses the shared GET transport with validated output and cancellation', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json(complete));
    const signal = new AbortController().signal;
    expect(await http(request).filesystem.getBreadcrumbs(fileId, signal)).toEqual(complete);
    expect(request).toHaveBeenCalledExactlyOnceWith('/api/me/filesystem/nodes/' + fileId + '/breadcrumbs', expect.objectContaining({ method: 'GET', signal, credentials: 'same-origin' }));
  });

  test('invalid ids never request and invalid responses fail at the boundary', async (): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ items: [], complete: true }));
    const api = http(request).filesystem;
    expect(() => api.getBreadcrumbs('invalid')).toThrow();
    expect(request).not.toHaveBeenCalled();
    await expect(api.getBreadcrumbs(fileId)).rejects.toBeInstanceOf(SchemaValidationError);
  });

  test.each([401, 403, 500])('preserves %s failures without replay', async (status): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status }));
    const result = http(request).filesystem.getBreadcrumbs(fileId);
    if (status === 401) await expect(result).rejects.toBeInstanceOf(AuthenticationRequiredError);
    else await expect(result).rejects.toMatchObject({ status });
    expect(request).toHaveBeenCalledTimes(1);
  });
});
