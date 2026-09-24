import { describe, expect, test, vi } from 'vitest';
import { OpenApiConnectorSetupState } from './openapi-connector-setup-state.svelte';

function response(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200 });
}

describe('OpenApiConnectorSetupState', () => {
  test('opens create mode with None authentication', () => {
    const state = new OpenApiConnectorSetupState();

    state.showCreate({ focus: vi.fn() } as unknown as HTMLElement);

    expect(state.open).toBe(true);
    expect(state.mode).toBe('create');
    expect(state.authenticationType).toBe('none');
    expect(state.configuredBearer).toBe(false);
  });

  test('opens configure mode with a validated masked Bearer configuration', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: '********'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiConnectorSetupState(request);

    await state.showConfigure({ focus: vi.fn() } as unknown as HTMLElement, 'billing', 'Billing', 'Billing', 'Manage billing resources');

    expect(state.mode).toBe('configure');
    expect(state.authenticationType).toBe('bearer');
    expect(state.configuredBearer).toBe(true);
    expect(JSON.stringify(state)).not.toContain('private-token');
  });

  test('retrieves a URL document and adds it to setup submission data', async () => {
    const request = vi.fn(async () => response({ openapi: '3.1.0', paths: {} })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiConnectorSetupState(request);
    state.showCreate({ focus: vi.fn() } as unknown as HTMLElement);
    state.setImportMode('url');
    state.replaceSpecificationUrl('https://example.com/openapi.json');
    const formData = new FormData();

    await expect(state.prepareSubmission(formData)).resolves.toBe(true);
    expect(formData.get('importMode')).toBe('url');
    expect(JSON.parse(String(formData.get('document')))).toMatchObject({ openapi: '3.1.0' });
    expect(request).toHaveBeenCalledWith('https://example.com/openapi.json', {
      method: 'GET',
      credentials: 'omit',
      redirect: 'follow'
    });
  });

  test('rejects non-HTTPS specification URLs before fetching', async () => {
    const request = vi.fn() as unknown as typeof globalThis.fetch;
    const state = new OpenApiConnectorSetupState(request);
    state.showCreate({ focus: vi.fn() } as unknown as HTMLElement);
    state.setImportMode('url');
    state.replaceSpecificationUrl('http://example.com/openapi.json');

    await expect(state.prepareSubmission(new FormData())).resolves.toBe(false);
    expect(state.urlError).toContain('HTTPS URL');
    expect(request).not.toHaveBeenCalled();
  });

  test('exposes malformed configure responses as implementation errors', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: 'private-token'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiConnectorSetupState(request);

    await expect(state.showConfigure({ focus: vi.fn() } as unknown as HTMLElement, 'billing', 'Billing', 'Billing', 'Manage billing resources')).rejects.toThrow();
    expect(state.open).toBe(false);
  });
});
