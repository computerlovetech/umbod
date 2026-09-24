import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import type { Handle } from '@sveltejs/kit';
import { handle } from './hooks.server';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
    ...init
  });
}

function handleInput(url: string, fetch: typeof globalThis.fetch, resolve: ReturnType<typeof vi.fn>): Parameters<Handle>[0] {
  const request = new Request(url, { headers: { 'X-Auth-Request-Access-Token': 'proxy-jwt' } });
  return {
    event: { fetch, request, url: new URL(url), locals: {} },
    resolve
  } as unknown as Parameters<Handle>[0];
}

describe('server authentication hook', () => {
  let stdoutWrite: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    stdoutWrite = vi.spyOn(process.stdout, 'write').mockImplementation(() => true);
  });

  afterEach(() => {
    stdoutWrite.mockRestore();
  });

  test('redirects an expired admin session to sign in with the complete return path', async () => {
    const fetch = vi.fn(async () => jsonResponse({ detail: 'Expired' }, { status: 401 }));
    const resolve = vi.fn();

    const response = await handle(
      handleInput(
        'http://frontend/admin/connectors?configured=slack',
        fetch as unknown as typeof globalThis.fetch,
        resolve
      )
    );

    expect(response.status).toBe(303);
    expect(response.headers.get('location')).toBe('/oauth2/sign_in?rd=%2Fadmin%2Fconnectors%3Fconfigured%3Dslack');
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(resolve).not.toHaveBeenCalled();
  });

  test('does not redirect an authenticated user who lacks authorization', async () => {
    const fetch = vi.fn(async () => jsonResponse({ detail: 'Forbidden' }, { status: 403 }));
    const resolve = vi.fn(async () => new Response('page'));

    const response = await handle(handleInput('http://frontend/admin/connectors', fetch as unknown as typeof globalThis.fetch, resolve));

    expect(response.status).toBe(200);
    expect(resolve).toHaveBeenCalledOnce();
  });

  test('forwards a proxy access token when checking the current user', async () => {
    const fetch = vi.fn(async () => jsonResponse({ id: 'user-1', email: 'user@example.com', name: 'User' }));
    const resolve = vi.fn(async ({ locals }) => Response.json(locals.currentUser));

    const response = await handle(handleInput('http://frontend/admin', fetch as unknown as typeof globalThis.fetch, resolve));

    expect(fetch).toHaveBeenCalledWith('http://api:8000/admin/users', { headers: { authorization: 'proxy-jwt' } });
    await expect(response.json()).resolves.toMatchObject({ id: 'user-1', email: 'user@example.com', name: 'User' });
  });

  test('does not probe authentication for public or oauth routes', async () => {
    const fetch = vi.fn();
    const resolve = vi.fn(async () => new Response('public'));

    await handle(handleInput('http://frontend/oauth2/sign_in', fetch as unknown as typeof globalThis.fetch, resolve));

    expect(fetch).not.toHaveBeenCalled();
    expect(resolve).toHaveBeenCalledOnce();
  });

  test('emits an OpenTelemetry-compatible request record without query parameters', async () => {
    const fetch = vi.fn();
    const resolve = vi.fn(async () => new Response('public', { status: 201 }));

    await handle(handleInput('http://frontend/admin-free?token=secret', fetch as unknown as typeof globalThis.fetch, resolve));

    expect(stdoutWrite).toHaveBeenCalledOnce();
    const payload = JSON.parse(String(stdoutWrite.mock.calls[0][0]));
    expect(payload).toMatchObject({
      severity_text: 'INFO',
      severity_number: 9,
      body: 'http server request completed',
      attributes: {
        'logger.name': 'umbod.frontend',
        'http.request.method': 'GET',
        'http.response.status_code': 201,
        'url.path': '/admin-free',
        'server.address': 'frontend'
      },
      resource: { 'service.name': 'umbod-frontend' }
    });
    expect(payload.attributes).not.toHaveProperty('url.query');
    expect(payload.trace_id).toMatch(/^[a-f0-9]{32}$/);
    expect(payload.span_id).toMatch(/^[a-f0-9]{16}$/);
  });
});
