import { afterEach, describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { AuthenticationRequiredError, HttpError, NetworkError, ResponseTooLargeError, SchemaValidationError, browserTransport, type Transport } from './transport';
import { InMemoryPublicConfigurationProvider } from './public-configuration';

afterEach(() => vi.unstubAllGlobals());

function streamedResponse(chunks: Uint8Array[], headers: HeadersInit = {}): { response: Response; cancel: ReturnType<typeof vi.fn> } {
  const cancel = vi.fn();
  let index = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(controller): void {
      if (index === chunks.length) controller.close();
      else controller.enqueue(chunks[index++]);
    },
    cancel
  });
  return { response: new Response(body, { headers }), cancel };
}

function configuredTransport(request: typeof fetch): Transport {
  return browserTransport({ fetch: request, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'http://localhost:8011' }) });
}

describe('bounded text responses', () => {
  test('accepts the exact byte limit and decodes characters split across chunks', async () => {
    const { response } = streamedResponse([new Uint8Array([0x61, 0xe2]), new Uint8Array([0x82, 0xac])], { 'Content-Length': '4' });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 4 }, outputSchema: z.string() })).resolves.toBe('a€');
    expect(response.body?.locked).toBe(false);
  });

  test.each([undefined, '1'])('enforces actual chunk bytes with content length %s', async (contentLength) => {
    const { response, cancel } = streamedResponse([new Uint8Array([0xe2, 0x82, 0xac]), new Uint8Array([0x61]), new Uint8Array([0x62])], contentLength === undefined ? {} : { 'Content-Length': contentLength });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 3 }, outputSchema: z.string() })).rejects.toMatchObject({ name: 'ResponseTooLargeError', maxBytes: 3 });
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });

  test('rejects excessive content length before reading and cancels the stream', async () => {
    const { response, cancel } = streamedResponse([new Uint8Array([0x61])], { 'Content-Length': '10' });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 3 }, outputSchema: z.string() })).rejects.toBeInstanceOf(ResponseTooLargeError);
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });

  test('cancels malformed UTF-8 streams and releases the reader', async () => {
    const { response, cancel } = streamedResponse([new Uint8Array([0xff]), new Uint8Array([0x61])]);
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 4 }, outputSchema: z.string() })).rejects.toBeInstanceOf(TypeError);
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });

  test('rejects incomplete UTF-8 at the end of the stream', async () => {
    const { response } = streamedResponse([new Uint8Array([0xe2, 0x82])]);
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 4 }, outputSchema: z.string() })).rejects.toBeInstanceOf(TypeError);
    expect(response.body?.locked).toBe(false);
  });

  test.each([0, -1, 1.5, NaN, Infinity])('rejects invalid byte limit %s before network access', async (maxBytes) => {
    const request = vi.fn<typeof fetch>();
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes }, outputSchema: z.string() })).rejects.toBeInstanceOf(RangeError);
    expect(request).not.toHaveBeenCalled();
  });

  test('validates decoded text with the output schema', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response('invalid'));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 10 }, outputSchema: z.literal('valid') })).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
  });

  test('validates an absent body as empty text', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 1 }, outputSchema: z.literal('') })).resolves.toBe('');
  });

  test('preserves authentication errors for text requests', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 1 }, outputSchema: z.string() })).rejects.toBeInstanceOf(AuthenticationRequiredError);
    expect(request).toHaveBeenCalledOnce();
  });

  test('preserves HTTP errors for text requests', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'Forbidden' }, { status: 403 }));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 1 }, outputSchema: z.string() })).rejects.toMatchObject({ status: 403, body: { detail: 'Forbidden' } });
  });

  test('preserves fetch cancellation errors and forwards the signal', async () => {
    const controller = new AbortController();
    controller.abort();
    const error = new DOMException('Aborted', 'AbortError');
    const request = vi.fn<typeof fetch>().mockRejectedValue(error);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', signal: controller.signal, responseBody: { kind: 'text', maxBytes: 1 }, outputSchema: z.string() })).rejects.toBe(error);
    expect(request).toHaveBeenCalledWith('/api/text', expect.objectContaining({ signal: controller.signal }));
  });

  test('preserves stream errors and releases the reader', async () => {
    const error = new DOMException('Aborted', 'AbortError');
    const body = new ReadableStream<Uint8Array>({ start(controller): void { controller.error(error); } });
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(body));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/text', responseBody: { kind: 'text', maxBytes: 1 }, outputSchema: z.string() })).rejects.toBe(error);
    expect(body.locked).toBe(false);
  });
});

describe('bounded byte responses', () => {
  test('preserves arbitrary binary bytes at the exact limit without UTF-8 decoding', async () => {
    const { response, cancel } = streamedResponse([new Uint8Array([0xff, 0x00, 0xc0]), new Uint8Array([0xaf, 0xe2, 0x82])], { 'Content-Length': '6' });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 6 }, outputSchema: z.instanceof(Uint8Array) })).resolves.toEqual(new Uint8Array([0xff, 0x00, 0xc0, 0xaf, 0xe2, 0x82]));
    expect(cancel).not.toHaveBeenCalled();
    expect(response.body?.locked).toBe(false);
  });

  test.each([undefined, '1'])('enforces actual bytes with content length %s and cancels the stream', async (contentLength: string | undefined) => {
    const { response, cancel } = streamedResponse([new Uint8Array([0xff, 0x00]), new Uint8Array([0x61, 0x62]), new Uint8Array([0x63])], contentLength === undefined ? {} : { 'Content-Length': contentLength });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 3 }, outputSchema: z.instanceof(Uint8Array) })).rejects.toMatchObject({ name: 'ResponseTooLargeError', maxBytes: 3 });
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });

  test('rejects excessive content length and cancels before consuming bytes', async () => {
    const { response, cancel } = streamedResponse([new Uint8Array([0xff])], { 'Content-Length': '10' });
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 3 }, outputSchema: z.instanceof(Uint8Array) })).rejects.toBeInstanceOf(ResponseTooLargeError);
    expect(cancel).toHaveBeenCalledOnce();
    expect(response.body?.locked).toBe(false);
  });

  test.each(['absent', 'empty stream'] as const)('returns an empty Uint8Array for an %s body', async (kind: 'absent' | 'empty stream') => {
    const response = kind === 'absent' ? new Response(null) : streamedResponse([]).response;
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 1 }, outputSchema: z.instanceof(Uint8Array) })).resolves.toEqual(new Uint8Array());
    expect(response.body?.locked ?? false).toBe(false);
  });

  test.each([0, -1, 1.5, NaN, Infinity])('rejects invalid byte limit %s before network access', async (maxBytes: number) => {
    const request = vi.fn<typeof fetch>();
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes }, outputSchema: z.instanceof(Uint8Array) })).rejects.toBeInstanceOf(RangeError);
    expect(request).not.toHaveBeenCalled();
  });

  test('validates binary output with the supplied schema and releases the reader', async () => {
    const { response } = streamedResponse([new Uint8Array([0xff])]);
    const request = vi.fn<typeof fetch>().mockResolvedValue(response);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 1 }, outputSchema: z.string() })).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'inbound' });
    expect(response.body?.locked).toBe(false);
  });

  test('preserves fetch cancellation errors and forwards the signal', async () => {
    const controller = new AbortController();
    controller.abort();
    const error = new DOMException('Aborted', 'AbortError');
    const request = vi.fn<typeof fetch>().mockRejectedValue(error);
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', signal: controller.signal, responseBody: { kind: 'bytes', maxBytes: 1 }, outputSchema: z.instanceof(Uint8Array) })).rejects.toBe(error);
    expect(request).toHaveBeenCalledWith('/api/bytes', expect.objectContaining({ signal: controller.signal }));
  });

  test('preserves stream cancellation errors and releases the reader', async () => {
    const error = new DOMException('Aborted', 'AbortError');
    const body = new ReadableStream<Uint8Array>({ start(controller): void { controller.error(error); } });
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(body));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 1 }, outputSchema: z.instanceof(Uint8Array) })).rejects.toBe(error);
    expect(body.locked).toBe(false);
  });

  test('preserves size errors and releases the reader when cancellation fails', async () => {
    const cancel = vi.fn().mockRejectedValue(new Error('Cancellation failed'));
    const body = new ReadableStream<Uint8Array>({
      pull(controller): void { controller.enqueue(new Uint8Array([0xff, 0x00])); },
      cancel
    });
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(body));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/bytes', responseBody: { kind: 'bytes', maxBytes: 1 }, outputSchema: z.instanceof(Uint8Array) })).rejects.toBeInstanceOf(ResponseTooLargeError);
    expect(cancel).toHaveBeenCalledOnce();
    expect(body.locked).toBe(false);
  });
});

describe('browser transport contract', () => {
  test('validates responses and marks same-origin requests', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ value: 'ready' }));
    const transport = configuredTransport(request);
    expect(await transport.request({ method: 'GET', path: '/admin/thing', outputSchema: z.object({ value: z.string() }) })).toEqual({ value: 'ready' });
    expect(request).toHaveBeenCalledWith('/api/admin/thing', expect.objectContaining({ method: 'GET', credentials: 'same-origin', headers: { 'X-Umbod-Web-Request': '1' } }));
  });
  test('rejects invalid outgoing payloads before requests', async () => {
    const request = vi.fn<typeof fetch>();
    await expect(configuredTransport(request).request({ method: 'POST', path: '/admin/thing', body: { value: 1 }, inputSchema: z.object({ value: z.string() }) })).rejects.toBeInstanceOf(SchemaValidationError);
    expect(request).not.toHaveBeenCalled();
  });
  test('validates incoming payloads', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ value: 1 }));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/admin/thing', outputSchema: z.object({ value: z.string() }) })).rejects.toMatchObject({ direction: 'inbound' });
  });
  test('encodes validated JSON with the browser marker', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 204 }));
    await configuredTransport(request).request({ method: 'PUT', path: '/admin/thing', body: { value: 'saved' }, inputSchema: z.object({ value: z.string() }) });
    expect(request).toHaveBeenCalledWith('/api/admin/thing', expect.objectContaining({ credentials: 'same-origin', headers: { 'X-Umbod-Web-Request': '1', 'content-type': 'application/json' }, body: '{"value":"saved"}' }));
  });
  test.each(['GET', 'DELETE'] as const)('rejects a single unauthorized %s request without navigation or replay', async (method) => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    await expect(configuredTransport(request).request({ method, path: '/admin/thing' })).rejects.toBeInstanceOf(AuthenticationRequiredError);
    expect(request).toHaveBeenCalledOnce();
    expect(assign).not.toHaveBeenCalled();
  });
  test('preserves forbidden failures without sign-in', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'Forbidden' }, { status: 403 }));
    const assign = vi.fn();
    vi.stubGlobal('window', { location: { assign } });
    await expect(configuredTransport(request).request({ method: 'GET', path: '/admin/thing' })).rejects.toBeInstanceOf(HttpError);
    expect(request).toHaveBeenCalledOnce();
    expect(assign).not.toHaveBeenCalled();
  });
  test('maps network failures', async () => {
    const request = vi.fn<typeof fetch>().mockRejectedValue(new Error('offline'));
    await expect(configuredTransport(request).request({ method: 'GET', path: '/admin/thing' })).rejects.toBeInstanceOf(NetworkError);
  });
  test('awaits public configuration before requests and carries cancellation', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({}));
    const get = vi.fn().mockResolvedValue({ apiBaseUrl: 'https://api.example.test/api', mcpBaseUrl: 'https://mcp.example.test' });
    const signal = new AbortController().signal;
    await browserTransport({ fetch: request, configuration: { get }, bearerToken: () => 'future-token' }).request({ method: 'GET', path: '/admin/thing', signal });
    expect(get).toHaveBeenCalledOnce();
    expect(request).toHaveBeenCalledWith('https://api.example.test/api/admin/thing', expect.objectContaining({ signal, credentials: 'same-origin', headers: { 'X-Umbod-Web-Request': '1', authorization: 'Bearer future-token' } }));
  });
});
