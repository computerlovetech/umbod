import { expect, test, vi } from 'vitest';
import { browserTransport } from '$lib/admin/infrastructure/transport';
import { InMemoryPublicConfigurationProvider } from '$lib/admin/infrastructure/public-configuration';
import { fileId } from '../fixtures.test-support';
import { FileContentRoute } from './file-content-route';
import type { PreviewReadFailure } from '../preview/ports';

const previewByteLimit = 257;

function route(request: typeof fetch): FileContentRoute {
  const configuration = new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: '/mcp', filesystemPreviewMaxBytes: previewByteLimit });
  return new FileContentRoute(browserTransport({ fetch: request, configuration }), configuration);
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

test.each(['text', 'bytes'] as const)('accepts the exact configured %s byte boundary', async (kind: 'text' | 'bytes'): Promise<void> => {
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('x'.repeat(previewByteLimit), { headers: { 'Content-Length': String(previewByteLimit) } }));
  const source = route(request);
  const result = kind === 'text' ? await source.readText(fileId, new AbortController().signal) : await source.readBytes(fileId, new AbortController().signal);
  expect(result).toHaveLength(previewByteLimit);
});

test.each(['text', 'bytes'] as const)('rejects oversized advertised %s content before consuming it', async (kind: 'text' | 'bytes'): Promise<void> => {
  const cancel = vi.fn<() => void>();
  const body = new ReadableStream<Uint8Array>({ cancel });
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(body, { headers: { 'Content-Length': String(previewByteLimit + 1) } }));
  const source = route(request);
  await expect(kind === 'text' ? source.readText(fileId, new AbortController().signal) : source.readBytes(fileId, new AbortController().signal)).rejects.toMatchObject({ reason: 'too-large' });
  expect(cancel).toHaveBeenCalledOnce();
});

test.each(['text', 'bytes'] as const)('rejects %s streaming beyond a smaller advertised size', async (kind: 'text' | 'bytes'): Promise<void> => {
  const cancel = vi.fn<() => void>();
  const body = new ReadableStream<Uint8Array>({
    start(controller): void {
      controller.enqueue(new Uint8Array(previewByteLimit));
      controller.enqueue(new Uint8Array(1));
    },
    cancel
  });
  const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(body, { headers: { 'Content-Length': '1' } }));
  const source = route(request);
  await expect(kind === 'text' ? source.readText(fileId, new AbortController().signal) : source.readBytes(fileId, new AbortController().signal)).rejects.toMatchObject({ reason: 'too-large' });
  expect(cancel).toHaveBeenCalledOnce();
});
