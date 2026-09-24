import { describe, expect, test, vi } from 'vitest';
import { z } from 'zod';
import { HttpError, SchemaValidationError, serverTransport } from './transport';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init
  });
}

function mockFetch(response: Response): ReturnType<typeof vi.fn> {
  return vi.fn(async () => response);
}

const itemSchema = z.object({ id: z.string() });

describe('serverTransport request pipeline', () => {
  test('returns parsed body when response matches output schema', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema })).resolves.toEqual({ id: 'a' });
    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', { method: 'GET' });
  });

  test('returns undefined when no output schema is provided', async () => {
    const fetch = mockFetch(new Response('', { status: 200, statusText: 'OK' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'DELETE', path: '/thing' })).resolves.toBeUndefined();
  });

  test('throws SchemaValidationError on inbound shape mismatch', async () => {
    const fetch = mockFetch(jsonResponse({ id: 42 }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema })).rejects.toMatchObject({
      name: 'SchemaValidationError',
      direction: 'inbound'
    });
  });

  test('sends JSON body and content-type when inputSchema accepts body', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);
    const inputSchema = z.object({ name: z.string() });

    await transport.request({ method: 'PUT', path: '/thing', body: { name: 'hi' }, inputSchema, outputSchema: itemSchema });

    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name: 'hi' })
    });
  });

  test('sends validated multipart data without a content-type header', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);
    const form = new FormData();
    form.append('file', new File(['{}'], 'api.json', { type: 'application/json' }));
    form.append('approved_hosts', 'api.example.com');

    await transport.request({
      method: 'POST', path: '/thing', outputSchema: itemSchema,
      requestBody: { kind: 'multipart', form, metadata: { approved_hosts: ['api.example.com'] }, metadataSchema: z.object({ approved_hosts: z.array(z.string()) }) }
    });

    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', { method: 'POST', body: form });
  });

  test('blocks multipart fetch when metadata is invalid', async () => {
    const fetch = vi.fn();
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);
    await expect(transport.request({
      method: 'POST', path: '/thing', outputSchema: itemSchema,
      requestBody: { kind: 'multipart', form: new FormData(), metadata: { approved_hosts: [42] }, metadataSchema: z.object({ approved_hosts: z.array(z.string()) }) }
    })).rejects.toMatchObject({ name: 'SchemaValidationError', direction: 'outbound' });
    expect(fetch).not.toHaveBeenCalled();
  });

  test('forwards the configured auth header from the server request', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const request = new Request('http://frontend/admin', { headers: { Authorization: 'Bearer jwt' } });
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch, request);

    await transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema });

    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', { method: 'GET', headers: { authorization: 'Bearer jwt' } });
  });

  test('normalizes the oauth proxy access token header to the configured backend auth header', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const request = new Request('http://frontend/admin', { headers: { 'X-Auth-Request-Access-Token': 'proxy-jwt' } });
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch, request);

    await transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema });

    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', { method: 'GET', headers: { authorization: 'proxy-jwt' } });
  });

  test('prefers the configured auth header over proxy fallback headers', async () => {
    const fetch = mockFetch(jsonResponse({ id: 'a' }));
    const request = new Request('http://frontend/admin', {
      headers: { Authorization: 'Bearer configured', 'X-Auth-Request-Access-Token': 'proxy-jwt' }
    });
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch, request);

    await transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema });

    expect(fetch).toHaveBeenCalledWith('http://api:8000/thing', {
      method: 'GET',
      headers: { authorization: 'Bearer configured' }
    });
  });

  test('throws SchemaValidationError outbound before calling fetch', async () => {
    const fetch = vi.fn();
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);
    const inputSchema = z.object({ name: z.string() });

    await expect(
      transport.request({ method: 'PUT', path: '/thing', body: { name: 42 }, inputSchema, outputSchema: itemSchema })
    ).rejects.toBeInstanceOf(SchemaValidationError);
    expect(fetch).not.toHaveBeenCalled();
  });

  test('throws when body is provided without inputSchema', async () => {
    const fetch = vi.fn();
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'PUT', path: '/thing', body: { x: 1 }, outputSchema: itemSchema })).rejects.toThrow(
      /Missing inputSchema/
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  test('throws HttpError carrying status and parsed body on non-ok response', async () => {
    const fetch = mockFetch(jsonResponse({ message: 'nope' }, { status: 409, statusText: 'Conflict' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'PUT', path: '/thing', outputSchema: itemSchema })).rejects.toMatchObject({
      name: 'HttpError',
      status: 409,
      body: { message: 'nope' }
    });
  });

  test('HttpError body is null when the failure response has no JSON', async () => {
    const fetch = mockFetch(new Response('', { status: 500, statusText: 'Server Error' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema })).rejects.toMatchObject({
      name: 'HttpError',
      status: 500,
      body: null
    });
  });

  test('exposes HttpError as an Error subclass', async () => {
    const fetch = mockFetch(new Response('', { status: 404, statusText: 'Not Found' }));
    const transport = serverTransport(fetch as unknown as typeof globalThis.fetch);

    await expect(transport.request({ method: 'GET', path: '/thing', outputSchema: itemSchema })).rejects.toBeInstanceOf(HttpError);
  });
});
