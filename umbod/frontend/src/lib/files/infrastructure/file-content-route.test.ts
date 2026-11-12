import { expect, test, vi } from 'vitest';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { fileId } from '../fixtures.test-support';
import { FileContentRoute, previewByteLimit } from './file-content-route';
import type { PreviewReadFailure } from '../preview/ports';

function route(request: typeof fetch): FileContentRoute {
  return new FileContentRoute(browserTransport({
    fetch: request,
    configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp' })
  }));
}

test('reads content through authenticated, redirect-rejecting transport with cancellation', async (): Promise<void> => {
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('# Notes'));
  const signal = new AbortController().signal;
  expect(await route(request).readText(fileId, signal)).toBe('# Notes');
  expect(request).toHaveBeenCalledExactlyOnceWith('/api/me/filesystem/nodes/' + fileId + '/content?delivery=stream',
    expect.objectContaining({ method: 'GET', credentials: 'same-origin', redirect: 'error', signal, headers: { 'X-Umbod-Web-Request': '1' } }));
});

test('reads binary content without UTF8 decoding through the same authenticated stream', async (): Promise<void> => {
  const bytes = new Uint8Array([37, 80, 68, 70, 45, 255, 0, 128]);
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(bytes));
  expect(await route(request).readBytes(fileId, new AbortController().signal)).toEqual(bytes);
});

test.each<[number, PreviewReadFailure]>([[401, 'sign-in'], [403, 'denied'], [404, 'missing'], [500, 'error']])(
  'maps binary HTTP %s into preview-level failure %s',
  async (status: number, reason: PreviewReadFailure): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'private diagnostic' }, { status }));
    await expect(route(request).readBytes(fileId, new AbortController().signal)).rejects.toMatchObject({ reason });
  }
);

test('rejects binary files exceeding the preview byte limit', async (): Promise<void> => {
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(new Uint8Array(previewByteLimit + 1)));
  await expect(route(request).readBytes(fileId, new AbortController().signal)).rejects.toMatchObject({ reason: 'too-large' });
});

test('rejects invalid node IDs before making requests', async (): Promise<void> => {
  const request = vi.fn<typeof fetch>();
  await expect(route(request).readText('../secret', new AbortController().signal)).rejects.toThrow();
  expect(request).not.toHaveBeenCalled();
});

test.each<[number, PreviewReadFailure]>([[401, 'sign-in'], [403, 'denied'], [404, 'missing'], [500, 'error']])(
  'maps HTTP %s into preview-level failure %s',
  async (status: number, reason: PreviewReadFailure): Promise<void> => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'private diagnostic' }, { status }));
    await expect(route(request).readText(fileId, new AbortController().signal)).rejects.toMatchObject({ reason });
  }
);

test('rejects files exceeding the preview byte limit', async (): Promise<void> => {
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('x'.repeat(previewByteLimit + 1)));
  await expect(route(request).readText(fileId, new AbortController().signal)).rejects.toMatchObject({ reason: 'too-large' });
});
