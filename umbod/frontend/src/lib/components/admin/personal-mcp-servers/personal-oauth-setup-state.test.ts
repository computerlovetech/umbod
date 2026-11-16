import { describe, expect, test, vi } from 'vitest';
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

describe('personal OAuth pre-publication setup', (): void => {
  test('loads current saved validation without contacting provider discovery or changing existing publication', async (): Promise<void> => {
    const { state, setup, validationChanged, publicationChanged } = harness();
    setup.current = setup.validation;
    await state.load('personal');
    expect(state.validated).toBe(true);
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
    expect(validationChanged).toHaveBeenLastCalledWith('personal', true);
    expect(publicationChanged).toHaveBeenLastCalledWith('personal', 'published');
  });

  test('discovery presents unchecked candidates and saves nothing until scopes are explicitly approved', async (): Promise<void> => {
    const { state, setup, servers, validationChanged, publicationChanged } = harness();
    const replace = vi.spyOn(servers, 'replacePolicy');
    await state.load('personal');
    await state.discover();
    expect(state.discovery?.available_scopes).toEqual(['records:read', 'records:write']);
    expect(state.scopes).toEqual([]);
    expect(replace).not.toHaveBeenCalled();
    state.toggleScope('records:read', true);
    state.toggleScope('not-advertised', true);
    expect(state.scopes).toEqual(['records:read']);
    expect(replace).not.toHaveBeenCalled();
    await state.approveSelectedScopes();
    expect(replace).toHaveBeenCalledExactlyOnceWith('personal', { expected_revision: 'r1', settings: { requested_scopes: ['records:read'], client: { kind: 'dynamic_public' } } });
    expect(state.validated).toBe(false);
    expect(validationChanged).toHaveBeenLastCalledWith('personal', false);
    expect(publicationChanged).toHaveBeenLastCalledWith('personal', 'unpublished');
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(0);
    const revision = setup.current.revision;
    await state.validate();
    expect(state.validated).toBe(true);
    expect(setup.calls.at(-1)).toMatchObject({ operation: 'validation', input: { expected_revision: revision } });
  });

  test('approving additional suggestions preserves existing manually configured scopes', async (): Promise<void> => {
    const { state, servers } = harness();
    await servers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: ['custom.read'], client: { kind: 'dynamic_public' } } });
    await state.load('personal');
    await state.discover();
    expect(state.scopes).toEqual(['custom.read']);
    state.toggleScope('records:read', true);
    await state.approveSelectedScopes();
    expect((await servers.policy('personal')).requested_scopes).toEqual(['custom.read', 'records:read']);
  });

  test.each([
    ['pkce_s256_required', 'PKCE S256'],
    ['registration_unavailable', 'Configure an existing client ID'],
    ['issuer_mismatch', 'explicitly approve the correct issuer']
  ] as const)('explains the fixed %s compatibility failure', async (reason, guidance): Promise<void> => {
    const { state, setup } = harness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason });
    await state.load('personal');
    await state.validate();
    expect(state.validated).toBe(false);
    expect(state.message).toContain(guidance);
  });

  test('scope mismatch shows both sets and approval is a separate revision-safe write', async (): Promise<void> => {
    const { state, setup, servers } = harness();
    setup.validation = setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: ['records:write'], downstream_response: { kind: 'http_response', status_code: 201 } } });
    const replace = vi.spyOn(servers, 'replacePolicy');
    await state.load('personal');
    await state.validate();
    expect(state.validated).toBe(false);
    expect(state.policy?.requested_scopes).toEqual([]);
    expect(state.returnedScopes).toEqual(['records:write']);
    expect(replace).not.toHaveBeenCalled();
    await state.approveSuggestedScopes();
    expect((await servers.policy('personal')).requested_scopes).toEqual(['records:write']);
    expect(state.status?.state.status).toBe('required');
    expect(state.message).toContain('Validate setup again');
  });

  test('discovered issuer never silently replaces configured issuer', async (): Promise<void> => {
    const { servers } = harness();
    await servers.replacePolicy('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'preconfigured_public', issuer_url: 'https://configured.test', client_id: 'app' } } });
    const setup = new InMemoryPersonalOAuthSetup();
    const revision = (await servers.policy('personal')).revision;
    setup.bindPolicies(servers);
    setup.current.policy_revision = revision;
    setup.discovery.policy_revision = revision;
    const local = new PersonalOAuthSetupState(setup, servers, vi.fn(), vi.fn(), vi.fn(), vi.fn());
    await local.load('personal');
    await local.discover();
    expect((await servers.policy('personal')).client).toMatchObject({ issuer_url: 'https://configured.test' });
    await local.acceptIssuer();
    expect((await servers.policy('personal')).client).toMatchObject({ issuer_url: 'https://issuer.test' });
  });

  test('duplicate requests and edits are blocked while registration is pending', async (): Promise<void> => {
    const { state, setup, lockChanged } = harness();
    const pending = deferred<SetupStatus>();
    const validate = vi.spyOn(setup, 'validate').mockReturnValueOnce(pending.promise);
    await state.load('personal');
    const operation = state.validate();
    await state.validate();
    await state.discover();
    await state.approveSelectedScopes();
    state.toggleScope('records:read', true);
    expect(state.locked).toBe(true);
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
    const operation = state.validate();
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
    await state.validate();
    await state.discover();
    await state.refresh();
    expect(state.accessDenied).toBe(true);
    expect(state.policy).toBeNull();
    expect(state.status).toBeNull();
    expect(accessLost).toHaveBeenCalledOnce();
    expect(state.message).not.toContain('provider-secret');
  });

  test('unknown registration outcome blocks replay until an explicit authoritative status refresh', async (): Promise<void> => {
    const { state, setup } = harness();
    await state.load('personal');
    const validate = vi.spyOn(setup, 'validate').mockRejectedValueOnce(new NetworkError(new Error('provider-secret')));
    await state.validate();
    await state.validate();
    expect(validate).toHaveBeenCalledTimes(1);
    expect(state.requiresRefresh).toBe(true);
    expect(state.message).toContain('Registration may have occurred');
    expect(state.message).not.toContain('provider-secret');
    setup.current = setup.validation;
    await state.refresh();
    expect(state.validated).toBe(true);
  });

  test('completed provider failure allows only an explicit new attempt after checking settings', async (): Promise<void> => {
    const { state, setup } = harness();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'registration', reason: 'provider_rejected' });
    await state.load('personal');
    await state.validate();
    expect(state.validated).toBe(false);
    expect(state.locked).toBe(false);
    expect(state.message).toContain('before explicitly trying again');
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
    await state.validate();
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(2);
  });

  test('in-progress status is never retried automatically and policy changes invalidate displayed success', async (): Promise<void> => {
    const { state, setup, validationChanged } = harness();
    setup.current = setupFixture({ status: 'in_progress', operation: 'validation', attempt_id: 'attempt', lease_expires_at: '2026-01-01T00:00:00Z' });
    await state.load('personal');
    await state.validate();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
    expect(state.requiresRefresh).toBe(true);
    setup.current = setup.validation;
    await state.refresh();
    expect(state.validated).toBe(true);
    state.policyChanged(serverFixture());
    expect(state.validated).toBe(false);
    expect(validationChanged).toHaveBeenLastCalledWith('personal', false);
    await vi.waitFor(() => expect(state.pending).toBeNull());
  });
});
