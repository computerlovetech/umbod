import { describe, expect, test, vi } from 'vitest';

const connector = {
  connector_id: 'billing',
  display_name: 'Billing API',
  tool_name_prefix: 'Billing_API',
  capability_description: 'Manage billing resources',
  base_capability_description: 'Manage billing resources',
  effective_capability_description: 'Manage billing resources',
  capability_description_override: { state: 'system', revision: 0 },
  created_at: '2026-03-01T10:00:00Z',
  updated_at: '2026-03-02T10:00:00Z',
  publication_status: 'unpublished',
  available_actions: ['import', 'publish']
};

describe('OpenAPI connector administration milestone 2', () => {
  test('create action trims the name, authenticates the API request, and redirects to the list workspace', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const fetch = vi.fn(async () => new Response(JSON.stringify(connector), { status: 201 })) as typeof globalThis.fetch;
    const request = new Request('http://frontend/admin/openapi-connectors?/create', {
      method: 'POST',
      headers: { authorization: 'Bearer admin' },
      body: new URLSearchParams({ displayName: '  Billing API  ', toolNamePrefix: 'Billing_API', capabilityDescription: '  Manage billing resources  ' })
    });
    await expect(actions.create({ fetch, request } as never)).rejects.toMatchObject({
      status: 303,
      location: '/admin/openapi-connectors?connector=billing'
    });
    expect(fetch).toHaveBeenCalledWith(
      'http://api:8000/admin/connectors/openapi',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ display_name: 'Billing API', tool_name_prefix: 'Billing_API', capability_description: 'Manage billing resources' }),
        headers: expect.objectContaining({ authorization: 'Bearer admin' })
      })
    );
  });

  test('create action preserves invalid input and returns safe inline errors', async () => {
    const { actions } = await import('../../routes/admin/openapi-connectors/+page.server');
    const invalidRequest = new Request('http://frontend/admin/openapi-connectors?/create', {
      method: 'POST',
      body: new URLSearchParams({ displayName: '   ', capabilityDescription: 'Manage billing resources' })
    });
    await expect(actions.create({ fetch: vi.fn(), request: invalidRequest } as never)).resolves.toEqual({
      status: 'invalid',
      displayName: '   ',
      message: 'Enter a display name'
    });
    const unavailableRequest = new Request('http://frontend/admin/openapi-connectors?/create', {
      method: 'POST',
      body: new URLSearchParams({ displayName: 'Billing API', toolNamePrefix: 'Billing_API', capabilityDescription: 'Manage billing resources' })
    });
    await expect(
      actions.create({
        fetch: vi.fn(async () => new Response('secret backend body', { status: 503 })),
        request: unavailableRequest
      } as never)
    ).resolves.toEqual({
      status: 'failed',
      displayName: 'Billing API',
      message: 'OpenAPI connector creation is unavailable. Try again.'
    });
  });

  test('detail route redirects into the list workspace with the connector selected', async () => {
    const { load } = await import('../../routes/admin/openapi-connectors/[connectorId]/+page.server');
    expect(() => load({ params: { connectorId: 'billing' } } as never)).toThrow(
      expect.objectContaining({
        status: 303,
        location: '/admin/openapi-connectors?connector=billing'
      })
    );
  });
});
