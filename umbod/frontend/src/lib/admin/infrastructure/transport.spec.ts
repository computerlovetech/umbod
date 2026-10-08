import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError, browserTransport, type Transport } from './transport';
import { InMemoryPublicConfigurationProvider } from './public-configuration';

function configuredTransport(request: typeof fetch, signIn = vi.fn()): Transport {
  return browserTransport({ fetch: request, signIn, configuration: new InMemoryPublicConfigurationProvider({ apiBaseUrl: '/api', mcpBaseUrl: 'http://localhost:8011' }) });
}

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
  test('redirects expired mutations centrally without exposing an operational retry', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 401 }));
    const signIn = vi.fn();
    await expect(configuredTransport(request, signIn).request({ method: 'DELETE', path: '/admin/thing' })).rejects.toBeInstanceOf(AuthenticationRequiredError);
    expect(signIn).toHaveBeenCalledOnce();
  });
  test('preserves forbidden failures without sign-in', async () => {
    const request = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ detail: 'Forbidden' }, { status: 403 }));
    const signIn = vi.fn();
    await expect(configuredTransport(request, signIn).request({ method: 'GET', path: '/admin/thing' })).rejects.toBeInstanceOf(HttpError);
    expect(signIn).not.toHaveBeenCalled();
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
