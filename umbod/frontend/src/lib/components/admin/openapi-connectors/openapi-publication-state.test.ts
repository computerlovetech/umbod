import { describe, expect, test, vi } from 'vitest';
import { OpenApiPublicationState } from './openapi-publication-state.svelte';

describe('OpenApiPublicationState', () => {
  test('requests, cancels, and confirms publication', () => {
    const state = new OpenApiPublicationState();
    const form = { requestSubmit: vi.fn() } as unknown as HTMLFormElement;

    state.request(form, 'Billing API', 'Publish');
    expect(state.modalTitle).toBe('Publish Billing API?');
    expect(state.modalMessage).toContain('publish the OpenAPI connector Billing API');

    state.cancel();
    expect(state.pendingPublication).toBeNull();

    state.request(form, 'Billing API', 'Unpublish');
    state.confirm();
    expect(form.requestSubmit).toHaveBeenCalledOnce();
    expect(state.pendingPublication).toBeNull();
  });
});
