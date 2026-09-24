import { describe, expect, test, vi } from 'vitest';
import { OpenApiBearerConfigurationState } from './openapi-bearer-configuration-state.svelte';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('OpenApiBearerConfigurationState', () => {
  test('loads only masked configuration state and never places a secret in the token field', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: '********'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiBearerConfigurationState('billing', request);

    await state.load();

    expect(state.configured).toBe(true);
    expect(state.token).toBe('');
    expect(request).toHaveBeenCalledWith('/admin/openapi-connectors/billing/configuration');
  });

  test('submits the entered token and clears it after a successful save', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: '********'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiBearerConfigurationState('billing', request);
    await state.load();
    state.setTokenValue('private-token');

    await state.save({ preventDefault: vi.fn() } as unknown as SubmitEvent);

    expect(request).toHaveBeenLastCalledWith('/admin/openapi-connectors/billing/configuration', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ bearer_token: 'private-token' })
    });
    expect(state.token).toBe('');
    expect(state.message).toBe('Bearer token saved.');
  });

  test('submits a blank configured token without introducing a masked value into state', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: '********'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiBearerConfigurationState('billing', request);
    await state.load();

    await state.save({ preventDefault: vi.fn() } as unknown as SubmitEvent);

    expect(request).toHaveBeenLastCalledWith('/admin/openapi-connectors/billing/configuration', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ bearer_token: '' })
    });
    expect(state.configured).toBe(true);
    expect(state.token).toBe('');
  });

  test('exposes malformed configuration responses', async () => {
    const request = vi.fn(async () => response({
      configured: true,
      authentication_type: 'bearer',
      masked_token: 'private-token'
    })) as unknown as typeof globalThis.fetch;
    const state = new OpenApiBearerConfigurationState('billing', request);

    await expect(state.load()).rejects.toThrow();
    expect(state.configured).toBe(false);
    expect(state.token).toBe('');
  });
});
