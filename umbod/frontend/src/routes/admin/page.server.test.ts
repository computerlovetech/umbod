import { describe, expect, test, vi } from 'vitest';
import { SchemaValidationError } from '$lib/admin/infrastructure/transport';
import { load } from './+page.server';
import { load as universalLoad } from './+page';

function loadEvent(fetch: typeof globalThis.fetch): Parameters<typeof load>[0] {
  return { fetch, request: new Request('http://frontend/admin') } as Parameters<typeof load>[0];
}

function emptyResponse(url: string | URL | Request): Response {
  return Response.json(String(url).endsWith('/groups') ? { groups: [] } : { connectors: [] });
}

describe('/admin overview server boundary', () => {
  test('loads successful empty lists and forwards server data through the universal loader', async () => {
    const fetch = vi.fn(async (url: string | URL | Request): Promise<Response> => emptyResponse(url));
    const data = await load(loadEvent(fetch as typeof globalThis.fetch));
    expect(data).toMatchObject({ overview: { configured: { status: 'available', value: 0 }, tools: { status: 'available', value: { enabled: 0, known: 0 } } } });
    expect(fetch).toHaveBeenCalledTimes(4);
    expect(universalLoad({ data: data as Parameters<typeof universalLoad>[0]['data'] }).overview).toEqual(data?.overview);
    expect(universalLoad().navigationItems).toHaveLength(4);
  });

  test.each([401, 403])('propagates authorization status %i as a SvelteKit error', async (status) => {
    const fetch = vi.fn(async (): Promise<Response> => Response.json({ detail: 'Access denied' }, { status, statusText: 'Access denied' }));
    await expect(load(loadEvent(fetch as typeof globalThis.fetch))).rejects.toMatchObject({ status });
  });

  test('an operational HTTP list failure leaves independent sources available', async () => {
    const fetch = vi.fn(async (url: string | URL | Request): Promise<Response> => String(url).endsWith('/openapi') ? Response.json({}, { status: 503 }) : emptyResponse(url));
    await expect(load(loadEvent(fetch as typeof globalThis.fetch))).resolves.toMatchObject({ overview: {
      configured: { status: 'unavailable' }, permissionGroups: { status: 'available', value: 0 },
      breakdown: [{ kind: 'catalog', connectors: { status: 'available' } }, { kind: 'openapi', connectors: { status: 'unavailable' } }, { kind: 'mcp', connectors: { status: 'available' } }]
    } });
  });

  test('a network failure marks only the relevant source unavailable', async () => {
    const fetch = vi.fn(async (url: string | URL | Request): Promise<Response> => {
      if (String(url).endsWith('/groups')) throw new TypeError('Connection refused');
      return emptyResponse(url);
    });
    await expect(load(loadEvent(fetch as typeof globalThis.fetch))).resolves.toMatchObject({ overview: { configured: { status: 'available', value: 0 }, permissionGroups: { status: 'unavailable' } } });
  });

  test.each([401, 403, 503])('handles tool HTTP status %i without losing authorization or connector counts', async (status) => {
    const fetch = vi.fn(async (url: string | URL | Request): Promise<Response> => {
      const path = String(url);
      if (path.endsWith('/tools')) return Response.json({}, { status, statusText: 'Tool request failed' });
      if (path.endsWith('/admin/connectors/catalog')) return Response.json({ connectors: [{ id: 'draft', display_name: 'Draft', description: '', extension: { source: 'built-in' }, publication_status: 'draft', available_actions: [] }] });
      return emptyResponse(url);
    });
    const loading = load(loadEvent(fetch as typeof globalThis.fetch));
    if (status === 401 || status === 403) {
      await expect(loading).rejects.toMatchObject({ status });
    } else {
      await expect(loading).resolves.toMatchObject({ overview: { configured: { status: 'available', value: 1 }, tools: { status: 'unavailable' }, attention: { status: 'available', value: { draft: 1 } } } });
    }
  });

  test('does not hide invalid payloads as unavailable data', async () => {
    const fetch = vi.fn(async (): Promise<Response> => Response.json({ unexpected: true }));
    await expect(load(loadEvent(fetch as typeof globalThis.fetch))).rejects.toBeInstanceOf(SchemaValidationError);
  });

  test('does not hide response parsing errors as unavailable data', async () => {
    const fetch = vi.fn(async (): Promise<Response> => new Response('not JSON'));
    await expect(load(loadEvent(fetch as typeof globalThis.fetch))).rejects.toBeInstanceOf(SyntaxError);
  });
});
