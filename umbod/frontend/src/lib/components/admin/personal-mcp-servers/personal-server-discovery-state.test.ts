import { describe, expect, test, vi } from 'vitest';
import type { EndpointDiscoveryResult } from '$lib/admin/personal-mcp-servers/domain/discovery';
import type { PersonalServerDiscovery } from '$lib/admin/personal-mcp-servers/discovery-administration';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { PersonalServerDiscoveryState } from './personal-server-discovery-state.svelte';
import { PolicyForm } from './policy-form.svelte';
import { policyFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';

const endpoint = 'https://mcp.test/mcp';
function discovered(overrides: Partial<Extract<EndpointDiscoveryResult, { kind: 'discovered' }>> = {}): Extract<EndpointDiscoveryResult, { kind: 'discovered' }> {
  return { kind: 'discovered', endpoint_url: endpoint, issuer_url: 'https://Issuer.test:443/Exact/', available_scopes: ['read', 'write'], scope_source: 'resource', automatic_registration: 'available', token_endpoint_auth_methods: ['none'], ...overrides };
}
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}
function setup(): { state: PersonalServerDiscoveryState; api: PersonalServerDiscovery; lost: ReturnType<typeof vi.fn> } {
  const api: PersonalServerDiscovery = { discover: vi.fn(async () => discovered()) };
  const lost = vi.fn();
  const state = new PersonalServerDiscoveryState(api, lost);
  state.reset(true);
  state.setEndpoint(endpoint);
  return { state, api, lost };
}
describe('creation metadata discovery', (): void => {
  test('only blur requests once until explicit retry and all scopes start unchecked', async (): Promise<void> => {
    const { state, api } = setup();
    expect(api.discover).not.toHaveBeenCalled();
    await state.blur();
    await state.blur();
    expect(api.discover).toHaveBeenCalledExactlyOnceWith({ endpoint_url: endpoint, issuer_selection: { kind: 'automatic' } });
    expect(state.selectedScopes).toEqual([]);
    expect(state.scopeSummary).toBe('No explicit scopes');
    expect(state.canSave('dynamic_public')).toBe(false);
    state.approve(true);
    expect(state.canSave('dynamic_public')).toBe(true);
    await state.retry();
    expect(api.discover).toHaveBeenCalledTimes(2);
    expect(state.approved).toBe(false);
  });
  test.each(['http://mcp.test', 'https://mcp.test/mcp?query=1', 'not a url'])('does not request invalid discovery endpoint %s', async (value): Promise<void> => {
    const { state, api } = setup();
    state.setEndpoint(value);
    await state.blur();
    expect(api.discover).not.toHaveBeenCalled();
    expect(state.canSave('dynamic_public')).toBe(false);
  });
  test.each(['edit', 'reopen', 'dispose'] as const)('fences late success and authentication errors after %s without stranding pending', async (action): Promise<void> => {
    for (const failure of [false, true]) {
      const { state, api, lost } = setup();
      const pending = deferred<EndpointDiscoveryResult>();
      vi.mocked(api.discover).mockReturnValueOnce(pending.promise);
      const operation = state.blur();
      expect(state.pending).toBe(true);
      if (action === 'edit') state.setEndpoint('https://b.test/mcp');
      else { state.reset(false); if (action === 'reopen') { state.reset(true); state.setEndpoint(endpoint); } }
      expect(state.pending).toBe(false);
      if (action !== 'dispose') await state.blur();
      const current = state.result;
      if (failure) pending.reject(new HttpError(403, '', null)); else pending.resolve(discovered());
      await operation;
      expect(state.result).toEqual(current);
      expect(state.pending).toBe(false);
      expect(lost).not.toHaveBeenCalled();
    }
  });
  test.each([401, 403])('access loss %s never enables manual fallback', async (status): Promise<void> => {
    const { state, api, lost } = setup();
    vi.mocked(api.discover).mockRejectedValueOnce(new HttpError(status, '', null));
    await state.blur();
    state.configureManually();
    state.acknowledge(true);
    expect(lost).toHaveBeenCalledOnce();
    expect(state.failed).toBe(false);
    expect(state.canSave('dynamic_public')).toBe(false);
  });
  test.each(['resource', 'authorization_server', 'unavailable'] as const)('retains known empty and unavailable scope source %s', async (source): Promise<void> => {
    const { state, api } = setup();
    vi.mocked(api.discover).mockResolvedValueOnce(discovered({ scope_source: source, available_scopes: [] }));
    await state.blur();
    expect(state.result?.scope_source).toBe(source);
    expect(state.scopes).toEqual([]);
  });
  test('scope validation includes custom and selected tokens and changes revoke approval', async (): Promise<void> => {
    const { state } = setup();
    await state.blur();
    state.toggleScope('write', true);
    state.setCustomScopes('custom');
    state.approve(true);
    expect(state.proposal).toEqual({ issuer: discovered().issuer_url, scopes: ['custom', 'write'] });
    state.setCustomScopes('write');
    expect(state.scopeError).toContain('unique ASCII');
    expect(state.approved).toBe(false);
    for (const invalid of ['bad\u00a0scope', 'x'.repeat(257), Array.from({ length: 65 }, (_, index) => `scope${index}`).join(' ')]) {
      state.setCustomScopes(invalid);
      state.approve(true);
      expect(state.canSave('dynamic_public')).toBe(false);
    }
  });
  test('requires advertised issuer selection and repeats discovery with exact selection', async (): Promise<void> => {
    const { state, api } = setup();
    vi.mocked(api.discover).mockResolvedValueOnce({ kind: 'issuer_selection_required', endpoint_url: endpoint, issuer_urls: ['https://one.test', 'https://two.test'] });
    await state.blur();
    expect(state.selectedIssuer).toBe('');
    expect(state.canSave('dynamic_public')).toBe(false);
    await state.selectIssuer('https://unadvertised.test');
    expect(api.discover).toHaveBeenCalledTimes(1);
    vi.mocked(api.discover).mockResolvedValueOnce(discovered({ issuer_url: 'https://two.test' }));
    await state.selectIssuer('https://two.test');
    expect(api.discover).toHaveBeenLastCalledWith({ endpoint_url: endpoint, issuer_selection: { kind: 'selected', issuer_url: 'https://two.test' } });
    expect(state.issuers).toEqual(['https://one.test', 'https://two.test']);
    expect(state.approved).toBe(false);
  });
  test('unsupported automatic registration cannot be bypassed by manual acknowledgement', async (): Promise<void> => {
    const { state, api } = setup();
    vi.mocked(api.discover).mockResolvedValueOnce(discovered({ automatic_registration: 'unavailable' }));
    await state.blur();
    state.approve(true);
    state.configureManually();
    state.acknowledge(true);
    expect(state.canSave('dynamic_public')).toBe(false);
    expect(state.canSave('preconfigured_public')).toBe(true);
    vi.mocked(api.discover).mockRejectedValueOnce(new Error('metadata unavailable'));
    await state.retry();
    state.configureManually();
    state.acknowledge(true);
    expect(state.canSave('dynamic_public')).toBe(false);
    expect(state.canSave('preconfigured_public')).toBe(true);
  });
  test('failed metadata requires explicit manual configuration and acknowledgement', async (): Promise<void> => {
    const { state, api } = setup();
    vi.mocked(api.discover).mockRejectedValueOnce(new Error('private diagnostic'));
    await state.blur();
    expect(state.canSave('dynamic_public')).toBe(false);
    state.configureManually();
    expect(state.canSave('dynamic_public')).toBe(false);
    state.acknowledge(true);
    expect(state.canSave('dynamic_public')).toBe(true);
  });
  test('bound dynamic edit preserves exact issuer across scope edits and legacy remains unbound', (): void => {
    const form = new PolicyForm();
    form.reset({ ...policyFixture(), client: { kind: 'dynamic_public', approved_issuers: [discovered().issuer_url] } });
    form.set('scopes', 'read');
    expect(form.settings().client).toEqual({ kind: 'dynamic_public', approved_issuers: [discovered().issuer_url] });
    form.reset({ ...policyFixture(), client: { kind: 'dynamic_public' } });
    expect(form.settings().client).toEqual({ kind: 'dynamic_public' });
  });
});
