import { describe, expect, test, vi } from 'vitest';

type PageLoad = (event: { fetch: typeof fetch; request: Request; url: URL }) => Promise<unknown>;

describe('OpenAPI connector administration milestone 1', () => {
  test('admin overview groups OpenAPI connectors under the connector entry', async () => {
    const { load } = await import('../../routes/admin/+page');
    expect(load().navigationItems).toContainEqual({ label: 'Connectors', href: '/admin/connectors' });
    expect(load().navigationItems).not.toContainEqual({ label: 'OpenAPI connectors', href: '/admin/openapi-connectors' });
  });

  test('server load uses the authenticated private admin API and hydrates only selected detail', async () => {
    const { load } = (await import('../../routes/admin/openapi-connectors/+page.server')) as unknown as { load: PageLoad };
    const fetch = vi.fn(async (input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith('/billing/tools/activation')) {
        return new Response(JSON.stringify({ connector_id: 'billing', tools: [] }), { status: 200 });
      }
      if (url.endsWith('/billing')) {
        return new Response(JSON.stringify({
          connector_id: 'billing', display_name: 'Billing API', tool_name_prefix: 'Billing_API', capability_description: 'Manage billing resources',
          base_capability_description: 'Manage billing resources', effective_capability_description: 'Manage billing resources',
          capability_description_override: { state: 'system', revision: 0 }, created_at: '2026-03-01T10:00:00Z', updated_at: '2026-03-02T10:00:00Z',
          publication_status: 'unpublished', available_actions: ['import', 'publish']
        }), { status: 200 });
      }
      return new Response(JSON.stringify({ connectors: [{
        connector_id: 'billing', display_name: 'Billing API',
        publication_status: 'unpublished', available_actions: ['import', 'publish']
      }] }), { status: 200 });
    }) as typeof globalThis.fetch;
    const request = new Request('http://frontend/admin/openapi-connectors', { headers: { authorization: 'Bearer admin' } });
    const data = await load({ fetch, request, url: new URL(request.url) });
    expect(fetch).toHaveBeenCalledWith('http://api:8000/admin/connectors/openapi', expect.objectContaining({ headers: { authorization: 'Bearer admin' } }));
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch).toHaveBeenNthCalledWith(2, 'http://api:8000/admin/connectors/openapi/billing', expect.objectContaining({ method: 'GET' }));
    expect(data).toMatchObject({
      status: 'ready',
      connectors: [{
        id: 'billing',
        name: 'Billing API',
        publicationStatus: 'Unpublished',
        canPublish: true,
        canUnpublish: false,
        canImport: true,
        tools: []
      }]
    });
  });
});
