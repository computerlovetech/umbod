import { afterEach, describe, expect, test, vi } from 'vitest';
import { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { InMemoryPersonalOAuthSetup, discoveryFixture, setupFixture } from '$lib/admin/personal-mcp-servers/setup.test-support';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { AuthenticationRequiredError, HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { SetupStatus } from '$lib/admin/personal-mcp-servers/domain/setup';

function harness(): { state: PersonalOAuthSetupState; setup: InMemoryPersonalOAuthSetup; servers: InMemoryPersonalServers; validationChanged: ReturnType<typeof vi.fn>; publicationChanged: ReturnType<typeof vi.fn>; accessLost: ReturnType<typeof vi.fn>; lockChanged: ReturnType<typeof vi.fn> } {
  const setup = new InMemoryPersonalOAuthSetup();
  const servers = new InMemoryPersonalServers([{ ...serverFixture(), publication_status: 'published' }], [policyFixture()]);
  setup.bindPolicies(servers);
  const validationChanged = vi.fn();
  const publicationChanged = vi.fn();
  const accessLost = vi.fn();
  const lockChanged = vi.fn();
  return { state: new PersonalOAuthSetupState(setup, servers, validationChanged, publicationChanged, accessLost, lockChanged), setup, servers, validationChanged, publicationChanged, accessLost, lockChanged };
}

function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

afterEach((): void => { vi.restoreAllMocks(); });

async function staticHarness(): Promise<ReturnType<typeof harness>> {
  const result = harness();
  await result.servers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'preconfigured_public', issuer_url: 'https://configured.test', client_id: 'app' } } });
  result.setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'issuer_mismatch' });
  return result;
}

describe('personal OAuth pre-publication setup', (): void => {
  test('readiness follows loading, required and current validated receipts', async (): Promise<void> => {
    const { state, setup } = harness();
    expect(state.outcome).toBe('required');
    expect(state.editProposal).toBeUndefined();
    const loading = state.load('personal');
    expect(state.outcome).toBe('loading');
    expect(state.canCheck).toBe(false);
    await loading;
    expect(state.outcome).toBe('required');
    expect(state.canCheck).toBe(true);
    await state.check();
    expect(state.outcome).toBe('ready');
    expect(state.editProposal).toBeUndefined();
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
  });

  test.each(['timeout', 'network_failure', 'unexpected_failure', 'provider_rejected', 'invalid_response', 'unsupported', 'resource_mismatch', 'issuer_mismatch', 'ambiguous_issuer', 'pkce_s256_required', 'authorization_code_required', 'code_response_required', 'client_auth_required', 'registration_unavailable', 'registration_contract_mismatch', 'scope_mismatch'] as const)('completed %s reports readiness without retrying', async (reason): Promise<void> => {
    const { state, setup } = harness();
    setup.current = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'registration', reason });
    await state.load('personal');
    const transient = ['timeout', 'network_failure', 'unexpected_failure'].includes(reason);
    expect(state.outcome).toBe(transient ? 'failed' : 'changes_required');
    expect(state.sidebarLabel('personal')).toBe(transient ? 'Check failed' : 'Changes required');
    expect(state.canCheck).toBe(true);
    expect(state.requiresRefresh).toBe(false);
    expect(state.editProposal).toBeUndefined();
    expect(state.message).not.toBe('');
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
  });

  test('discovered corrections use current requested scopes, not advertised scopes', async (): Promise<void> => {
    const { state, setup, servers } = harness();
    await servers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: ['custom.read'], client: { kind: 'dynamic_public' } } });
    setup.current = { ...setup.discovery, policy_revision: (await servers.policy('personal')).revision };
    const replace = vi.spyOn(servers, 'replacePolicy');
    await state.load('personal');
    expect(state.outcome).toBe('changes_required');
    expect(state.editProposal).toEqual({ issuer: 'https://issuer.test', scopes: ['custom.read'] });
    expect(replace).not.toHaveBeenCalled();
  });

  test.each(['other', 'stale'] as const)('a validated receipt with %s identity or revision cannot establish readiness', async (mismatch): Promise<void> => {
    const { state, setup, validationChanged } = harness();
    vi.spyOn(setup, 'status').mockResolvedValueOnce({ ...setup.validation, ...(mismatch === 'other' ? { connector_id: 'other' } : { policy_revision: 'stale' }) });
    await state.load('personal');
    expect(state.validated).toBe(false);
    expect(state.outcome).toBe('unknown');
    expect(state.canCheck).toBe(false);
    expect(state.editProposal).toBeUndefined();
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
  });

  test('conflicting checks require refresh without replay', async (): Promise<void> => {
    const { state, setup } = harness();
    await state.load('personal');
    const validate = vi.spyOn(setup, 'validate').mockRejectedValueOnce(new HttpError(409, '', { secret: 'private' }));
    await state.check();
    await state.check();
    expect(state.outcome).toBe('unknown');
    expect(state.message).toBe('Settings changed elsewhere. Refresh status before continuing.');
    expect(validate).toHaveBeenCalledOnce();
  });

  test('loads current saved validation without contacting provider discovery or changing existing publication', async (): Promise<void> => {
    const { state, setup, validationChanged, publicationChanged } = harness();
    setup.current = setup.validation;
    await state.load('personal');
    expect(state.validated).toBe(true);
    expect(state.sidebarLabel('personal')).toBe('Configuration ready');
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
    expect(validationChanged).toHaveBeenLastCalledWith('personal', true);
    expect(publicationChanged).toHaveBeenLastCalledWith('personal', 'published');
  });

  test('checking never mutates policy or proposes provider scopes after success', async (): Promise<void> => {
    const { state, servers, setup } = harness();
    const replace = vi.spyOn(servers, 'replacePolicy');
    await state.load('personal');
    await state.check();
    expect(state.discovery?.available_scopes).toEqual(['records:read', 'records:write']);
    expect(state.editProposal).toBeUndefined();
    expect(state.outcome).toBe('ready');
    expect(replace).not.toHaveBeenCalled();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });

  test('successful checking validates once without a separate discovery request', async (): Promise<void> => {
    const { state, setup } = harness();
    expect(state.canCheck).toBe(false);
    await state.load('personal');
    expect(state.canCheck).toBe(true);
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
    expect(state.validated).toBe(true);
    expect(state.discovery?.issuer_url).toBe('https://issuer.test');
  });

  test('static issuer recovery uses the authoritative receipt revision without changing settings', async (): Promise<void> => {
    const { state, setup, servers, validationChanged } = await staticHarness();
    const replace = vi.spyOn(servers, 'replacePolicy');
    const validate = vi.spyOn(setup, 'validate');
    await state.load('personal');
    await state.check();
    const receipt = await validate.mock.results[0].value;
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation', 'discovery']);
    expect(setup.calls.at(-1)?.input?.expected_revision).toBe(receipt.revision);
    expect(receipt.revision).not.toBe('setup-1');
    expect(state.message).toBe('The server requires a different authorization provider. Review the issuer in settings.');
    expect(state.outcome).toBe('changes_required');
    expect(state.editProposal).toEqual({ issuer: 'https://issuer.test', scopes: [] });
    expect(state.message).not.toContain('Discover settings');
    expect(state.validated).toBe(false);
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
    expect(replace).not.toHaveBeenCalled();
    expect((await servers.policy('personal')).client).toMatchObject({ issuer_url: 'https://configured.test' });
    expect(validate).toHaveBeenCalledOnce();
  });

  test.each([
    ['discovery', 'ambiguous_issuer'],
    ['discovery', 'provider_rejected'],
    ['registration', 'issuer_mismatch']
  ] as const)('static %s %s failure does not trigger discovery', async (stage, reason): Promise<void> => {
    const { state, setup } = await staticHarness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage, reason });
    await state.load('personal');
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });

  test('confidential issuer mismatch recovers metadata but requires Edit instead of client-secret replacement', async (): Promise<void> => {
    const { state, setup, servers } = harness();
    await servers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'preconfigured_confidential', issuer_url: 'https://configured.test', client_id: 'app', client_secret: 'secret', token_endpoint_auth_method: 'client_secret_post' } } });
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'issuer_mismatch' });
    await state.load('personal');
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation', 'discovery']);
    expect(state.message).toContain('Review the issuer in settings');
    expect(state.editProposal).toEqual({ issuer: 'https://issuer.test', scopes: [] });
    expect((await servers.policy('personal')).client).toMatchObject({ issuer_url: 'https://configured.test' });
  });

  test('an authoritative in-progress validation response never starts discovery or another check', async (): Promise<void> => {
    const { state, setup } = await staticHarness();
    setup.validation = setupFixture({ status: 'in_progress', operation: 'validation', attempt_id: 'attempt', lease_expires_at: '2026-01-01T00:00:00Z' });
    await state.load('personal');
    await state.check();
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
    expect(state.sidebarLabel('personal')).toBe('Checking configuration');
    expect(state.canCheck).toBe(false);
  });

  test('a mismatched validation receipt never triggers recovery discovery', async (): Promise<void> => {
    const { state, setup } = await staticHarness();
    vi.spyOn(setup, 'validate').mockResolvedValueOnce({ ...setup.validation, connector_id: 'other' });
    const discover = vi.spyOn(setup, 'discover');
    await state.load('personal');
    await state.check();
    expect(discover).not.toHaveBeenCalled();
    expect(state.requiresRefresh).toBe(true);
  });

  test('dynamic issuer mismatch does not trigger discovery', async (): Promise<void> => {
    const { state, setup } = harness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'issuer_mismatch' });
    await state.load('personal');
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });

  test('unknown static validation outcome never triggers discovery or automatic replay', async (): Promise<void> => {
    const { state, setup } = await staticHarness();
    const discover = vi.spyOn(setup, 'discover');
    const validate = vi.spyOn(setup, 'validate').mockRejectedValueOnce(new NetworkError(new Error('secret')));
    await state.load('personal');
    await state.check();
    await state.check();
    expect(validate).toHaveBeenCalledOnce();
    expect(discover).not.toHaveBeenCalled();
    expect(state.requiresRefresh).toBe(true);
    expect(state.sidebarLabel('personal')).toBe('Check unavailable');
  });

  test.each(['detach', 'dispose'] as const)('%s prevents a late issuer mismatch from starting discovery', async (action): Promise<void> => {
    const { state, setup } = await staticHarness();
    const pending = deferred<SetupStatus>();
    vi.spyOn(setup, 'validate').mockReturnValueOnce(pending.promise);
    const discover = vi.spyOn(setup, 'discover');
    await state.load('personal');
    const operation = state.check();
    state[action]();
    pending.resolve({ ...setup.validation, policy_revision: (await setup.status('personal')).policy_revision });
    await operation;
    expect(discover).not.toHaveBeenCalled();
    expect(state.status).toBeNull();
  });

  test('recovery discovery keeps the lock and fences late results after a new load', async (): Promise<void> => {
    const { state, setup, lockChanged } = await staticHarness();
    const pending = deferred<SetupStatus>();
    const discover = vi.spyOn(setup, 'discover').mockReturnValueOnce(pending.promise);
    await state.load('personal');
    const operation = state.check();
    await vi.waitFor(() => expect(discover).toHaveBeenCalledOnce());
    expect(state.canCheck).toBe(false);
    expect(state.sidebarLabel('personal')).toBe('Checking configuration');
    expect(lockChanged).toHaveBeenLastCalledWith(true);
    await state.check();
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
    state.detach();
    setup.current = { ...setup.current, state: { status: 'required' } };
    await state.load('personal');
    pending.resolve({ ...setup.discovery, policy_revision: setup.current.policy_revision });
    await operation;
    expect(state.status?.state.status).toBe('required');
    expect(state.discovery).toBeNull();
    expect(state.sidebarLabel('personal')).toBe('Check required');
  });

  test.each([
    [setupFixture(), 'Check required'],
    [setupFixture({ status: 'discovered', checked_at: '2026-01-01T00:00:00Z', discovery: discoveryFixture() }), 'Changes required'],
    [setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: [], downstream_response: { kind: 'no_response' } } }), 'Changes required'],
    [setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'issuer_mismatch' }), 'Changes required'],
    [setupFixture({ status: 'in_progress', operation: 'validation', attempt_id: 'attempt', lease_expires_at: '2026-01-01T00:00:00Z' }), 'Checking configuration']
  ])('saved status %j has honest sidebar label %s', async (status, label): Promise<void> => {
    const { state, setup } = harness();
    expect(state.sidebarLabel('personal')).toBe('Check unavailable');
    setup.current = status;
    const loading = state.load('personal');
    expect(state.sidebarLabel('personal')).toBe('Loading check');
    await loading;
    expect(state.sidebarLabel('personal')).toBe(label);
    expect(state.sidebarLabel('other')).toBe('Check unavailable');
    state.detach();
    expect(state.sidebarLabel('personal')).toBe('Check unavailable');
  });

  test.each([
    ['pkce_s256_required', 'does not support secure sign-in'],
    ['registration_unavailable', 'Use an existing client'],
    ['issuer_mismatch', 'Choose the correct provider in Edit']
  ] as const)('explains the fixed %s compatibility failure', async (reason, guidance): Promise<void> => {
    const { state, setup } = harness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason });
    await state.load('personal');
    await state.check();
    expect(state.validated).toBe(false);
    expect(state.message).toContain(guidance);
  });

  test('scope mismatch preserves requested permissions without preselecting provider permissions', async (): Promise<void> => {
    const { state, setup, servers } = harness();
    setup.validation = setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: ['records:write'], downstream_response: { kind: 'http_response', status_code: 201 } } });
    const replace = vi.spyOn(servers, 'replacePolicy');
    await state.load('personal');
    await state.check();
    expect(state.validated).toBe(false);
    expect(state.policy?.requested_scopes).toEqual([]);
    expect(state.returnedScopes).toEqual(['records:write']);
    expect(replace).not.toHaveBeenCalled();
    expect(state.editProposal).toEqual({ issuer: 'https://issuer.test', scopes: [] });
    expect(state.outcome).toBe('changes_required');
    expect(state.message).toContain('Review the requested permissions');
  });

  test('duplicate requests and edits are blocked while registration is pending', async (): Promise<void> => {
    const { state, setup, lockChanged } = harness();
    const pending = deferred<SetupStatus>();
    const validate = vi.spyOn(setup, 'validate').mockReturnValueOnce(pending.promise);
    await state.load('personal');
    const operation = state.check();
    await state.check();
    await state.check();
    expect(state.outcome).toBe('checking');
    expect(state.locked).toBe(true);
    expect(state.canCheck).toBe(false);
    expect(state.sidebarLabel('personal')).toBe('Checking configuration');
    expect(validate).toHaveBeenCalledExactlyOnceWith('personal', { expected_revision: 'setup-1' });
    expect(lockChanged).toHaveBeenLastCalledWith(true);
    pending.resolve(setup.validation);
    await operation;
    expect(state.validated).toBe(true);
    expect(lockChanged).toHaveBeenLastCalledWith(false);
  });

  test.each(['detach', 'dispose'] as const)('%s fences late validation results', async (action): Promise<void> => {
    const { state, setup, validationChanged } = harness();
    const pending = deferred<SetupStatus>();
    vi.spyOn(setup, 'validate').mockReturnValueOnce(pending.promise);
    await state.load('personal');
    const operation = state.check();
    state[action]();
    pending.resolve(setup.validation);
    await operation;
    expect(state.status).toBeNull();
    expect(state.validated).toBe(false);
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
  });

  test.each([new AuthenticationRequiredError(), new HttpError(403, '', { secret: 'provider-secret' })])('access loss clears protected state and suppresses further requests', async (error): Promise<void> => {
    const { state, setup, accessLost } = harness();
    await state.load('personal');
    vi.spyOn(setup, 'validate').mockRejectedValueOnce(error);
    await state.check();
    await state.check();
    await state.refresh();
    expect(state.accessDenied).toBe(true);
    expect(state.outcome).toBe('denied');
    expect(state.message).toContain('Sign in again');
    expect(state.canCheck).toBe(false);
    expect(state.sidebarLabel('personal')).toBe('Check unavailable');
    expect(state.policy).toBeNull();
    expect(state.status).toBeNull();
    expect(accessLost).toHaveBeenCalledOnce();
    expect(state.message).not.toContain('provider-secret');
  });

  test('unknown registration outcome blocks replay until an explicit authoritative status refresh', async (): Promise<void> => {
    const { state, setup } = harness();
    await state.load('personal');
    const validate = vi.spyOn(setup, 'validate').mockRejectedValueOnce(new NetworkError(new Error('provider-secret')));
    await state.check();
    await state.check();
    expect(validate).toHaveBeenCalledTimes(1);
    expect(state.requiresRefresh).toBe(true);
    expect(state.message).toBe('The check may have completed. Refresh status before starting another.');
    expect(state.outcome).toBe('unknown');
    expect(state.canCheck).toBe(false);
    expect(state.message).not.toContain('provider-secret');
    setup.current = setup.validation;
    await state.refresh();
    expect(state.validated).toBe(true);
  });

  test('completed provider failure allows only an explicit new attempt after checking settings', async (): Promise<void> => {
    const { state, setup } = harness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'registration', reason: 'provider_rejected' });
    await state.load('personal');
    await state.check();
    expect(state.validated).toBe(false);
    expect(state.locked).toBe(false);
    expect(state.message).toContain('Review the settings in Edit');
    expect(state.outcome).toBe('changes_required');
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
    await state.check();
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(2);
  });

  test('in-progress status is never retried automatically and policy changes invalidate displayed success', async (): Promise<void> => {
    const { state, setup, validationChanged } = harness();
    setup.current = setupFixture({ status: 'in_progress', operation: 'validation', attempt_id: 'attempt', lease_expires_at: '2026-01-01T00:00:00Z' });
    await state.load('personal');
    await state.check();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
    expect(state.requiresRefresh).toBe(true);
    expect(state.outcome).toBe('unknown');
    expect(state.canCheck).toBe(false);
    setup.current = setup.validation;
    await state.refresh();
    expect(state.validated).toBe(true);
    state.policyChanged(serverFixture());
    expect(state.validated).toBe(false);
    expect(validationChanged).toHaveBeenLastCalledWith('personal', false);
    await vi.waitFor(() => expect(state.pending).toBeNull());
  });
});
