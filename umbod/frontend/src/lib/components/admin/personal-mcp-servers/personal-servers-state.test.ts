import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture, summaryFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import type { PersonalPolicy } from '$lib/admin/personal-mcp-servers/domain/schemas';
import { PersonalServersState } from './personal-servers-state.svelte';
import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
import type { InstanceConfiguration } from '$lib/admin/instance-configuration';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';

function setup(): { api: PersonalServerAdministration; configuration: InstanceConfigurationRoute; state: PersonalServersState; memory: PersonalServerAdministration } {
  const memory: PersonalServerAdministration = new InMemoryPersonalServers([serverFixture()], [policyFixture()]);
  const api: PersonalServerAdministration = {
    list: vi.fn(() => memory.list()), get: vi.fn((id) => memory.get(id)), policy: vi.fn((id) => memory.policy(id)), create: vi.fn((input) => memory.create(input)), replacePolicy: vi.fn((id, input) => memory.replacePolicy(id, input)), publish: vi.fn((id) => memory.publish(id)), withdraw: vi.fn((id) => memory.withdraw(id)), delete: vi.fn((id) => memory.delete(id))
  };
  const configuration: InstanceConfigurationRoute = { get: vi.fn(async () => configurationFixture()) };
  return { api, configuration, state: new PersonalServersState(api, configuration), memory };
}
function confidential(state: PersonalServersState): void {
  state.form.setKind('preconfigured_confidential');
  state.form.set('issuer', 'https://Issuer.test:443/Exact/');
  state.form.set('clientId', 'app');
  state.form.set('secret', 'secret-sentinel');
}
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

describe('personal allowlist state through administration port', () => {
  test('registration is guarded until authoritative configuration resolves', async () => {
    const { api, configuration, state } = setup();
    const pending = deferred<InstanceConfiguration>();
    vi.mocked(configuration.get).mockReturnValueOnce(pending.promise);
    expect(state.canRegister).toBe(false);
    state.openCreate();
    expect(state.creating).toBe(false);
    const operation = state.reload();
    state.openCreate();
    await state.create();
    expect(api.list).toHaveBeenCalledTimes(1);
    expect(api.create).not.toHaveBeenCalled();
    pending.resolve(configurationFixture());
    await operation;
    expect(state.canRegister).toBe(true);
  });
  test.each(['disabled', 'missing', 'mistyped', 'failed'] as const)('%s configuration blocks registration without blocking separate controls', async (mode) => {
    const { api, configuration, state } = setup();
    const result = configurationFixture(false);
    if (mode === 'missing') result.groups = [];
    if (mode === 'mistyped') result.groups[0].entries[0] = { ...result.groups[0].entries[0], type: 'string', value: 'true' };
    if (mode === 'failed') vi.mocked(configuration.get).mockRejectedValueOnce(new Error('secret-sentinel'));
    else vi.mocked(configuration.get).mockResolvedValueOnce(result);
    await state.reload();
    expect(state.canRegister).toBe(false);
    expect(state.locked).toBe(false);
    expect(state.selected).not.toBeNull();
    state.openCreate();
    expect(state.creating).toBe(false);
    await state.create();
    expect(api.create).not.toHaveBeenCalled();
    expect(state.message).not.toContain('secret-sentinel');
    state.requestConfirmation('publish');
    await state.confirm();
    expect(api.publish).toHaveBeenCalledTimes(1);
  });
  test('failed configuration supports explicit reload and OAuth-disabled registration stays allowed', async () => {
    const { configuration, state } = setup();
    vi.mocked(configuration.get).mockRejectedValueOnce(new Error('secret-sentinel'));
    await state.reload();
    expect(state.availability.registration).toBe('unknown');
    vi.mocked(configuration.get).mockResolvedValueOnce(configurationFixture(true, false));
    await state.reload();
    expect(state.canRegister).toBe(true);
    expect(state.availability.authorization).toBe('disabled');
    state.openCreate();
    expect(state.creating).toBe(true);
  });
  test.each([new AuthenticationRequiredError(), new HttpError(401, 'secret-sentinel', null)])('configuration authentication loss clears owner state and forms', async (error) => {
    const { configuration, state } = setup();
    await state.reload();
    confidential(state);
    vi.mocked(configuration.get).mockRejectedValueOnce(error);
    await state.reload();
    expect(state.authenticationLost).toBe(true);
    expect(state.availability).toEqual({ registration: 'unknown', authorization: 'unknown' });
    expect(state.selected).toBeNull();
    expect(state.records).toEqual([]);
    expect(state.form.secret).toBe('');
    expect(state.metadata.name).toBe('');
    expect(state.message).not.toContain('secret-sentinel');
  });
  test.each(['superseded', 'disposed'] as const)('late %s configuration cannot restore availability', async (mode) => {
    const { configuration, state } = setup();
    const pending = deferred<InstanceConfiguration>();
    vi.mocked(configuration.get).mockReturnValueOnce(pending.promise);
    const operation = state.reload();
    if (mode === 'disposed') state.dispose();
    else {
      vi.mocked(configuration.get).mockResolvedValueOnce(configurationFixture(false));
      await state.reload();
    }
    pending.resolve(configurationFixture());
    await operation;
    expect(state.availability.registration).toBe(mode === 'disposed' ? 'unknown' : 'disabled');
    expect(state.canRegister).toBe(false);
  });
  test.each(['personal_connections_unavailable', 'proxy_not_found'] as const)('registration 404 %s never retries or infers settings from a generic error', async (code) => {
    const { api, configuration, state } = setup();
    await state.reload();
    state.openCreate();
    for (const [field, value] of Object.entries({ name: 'New server', prefix: 'new', description: 'Search records', path: 'new', endpoint: 'https://provider.test/mcp' })) state.setMetadata(field as keyof typeof state.metadata, value);
    confidential(state);
    vi.mocked(api.create).mockRejectedValueOnce(new HttpError(404, 'secret-sentinel', { detail: { code } }));
    await state.create();
    expect(state.availability.registration).toBe(code === 'personal_connections_unavailable' ? 'disabled' : 'unknown');
    expect(state.canRegister).toBe(false);
    expect(state.form.secret).toBe('');
    expect(state.message).not.toContain('secret-sentinel');
    await state.create();
    state.openCreate();
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(configuration.get).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.canRegister).toBe(true);
    expect(api.create).toHaveBeenCalledTimes(1);
  });
  test('initial load reads configuration, inventory, selected definition and policy', async () => {
    const { api, configuration, state } = setup();
    await state.reload();
    expect(state.records).toEqual([summaryFixture()]);
    expect(api.list).toHaveBeenCalledTimes(1);
    expect(configuration.get).toHaveBeenCalledTimes(1);
    expect(state.canRegister).toBe(true);
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.policy).toHaveBeenCalledTimes(1);
    for (const operation of [api.create, api.replacePolicy, api.publish, api.withdraw, api.delete]) expect(operation).not.toHaveBeenCalled();
  });
  test('registration stays unpublished with no implicit publication or grant action', async () => {
    const { api, state } = setup();
    await state.reload();
    state.openCreate();
    for (const [field, value] of Object.entries({ name: 'New server', prefix: 'new', description: 'Search records', path: 'new', endpoint: 'https://provider.test/mcp' })) state.setMetadata(field as keyof typeof state.metadata, value);
    await state.create();
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(state.selected?.publication_status).toBe('unpublished');
    expect(state.selected?.connector_id).toBe('new');
    expect(state.creating).toBe(false);
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.replacePolicy).not.toHaveBeenCalled();
  });
  test('registration close remains guarded while the native dialog mutation is busy', async () => {
    const { api, state } = setup();
    await state.reload();
    state.openCreate();
    for (const [field, value] of Object.entries({ name: 'New server', prefix: 'new', description: 'Search records', path: 'new', endpoint: 'https://provider.test/mcp' })) state.setMetadata(field as keyof typeof state.metadata, value);
    const pending = deferred<Awaited<ReturnType<PersonalServerAdministration['create']>>>();
    vi.mocked(api.create).mockReturnValueOnce(pending.promise);
    const operation = state.create();
    expect(state.busy).toBe(true);
    state.close();
    expect(state.creating).toBe(true);
    pending.reject(new HttpError(422, '', null));
    await operation;
    state.close();
    expect(state.creating).toBe(false);
  });
  test('an uncertain registration never replays and blocks all changes until explicit reload', async () => {
    const { api, state } = setup();
    await state.reload();
    state.openCreate();
    for (const [field, value] of Object.entries({ name: 'New server', prefix: 'new', description: 'Search records', path: 'new', endpoint: 'https://provider.test/mcp' })) state.setMetadata(field as keyof typeof state.metadata, value);
    confidential(state);
    vi.mocked(api.create).mockRejectedValueOnce(new NetworkError(new Error('secret-sentinel')));
    await state.create();
    expect(state.blocked).toBe(true);
    expect(state.form.secret).toBe('');
    expect(state.message).toContain('outcome is unknown');
    expect(state.message).not.toContain('secret-sentinel');
    await state.create();
    expect(api.create).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.blocked).toBe(false);
    expect(api.create).toHaveBeenCalledTimes(1);
  });
  test('confirmation precedes exactly one canonical revision-checked write and clears secret immediately', async () => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    state.form.set('scopes', 'z A');
    state.form.setMethod('client_secret_post');
    state.requestConfirmation('policy');
    expect(state.confirmation).toBe('policy');
    expect(api.replacePolicy).not.toHaveBeenCalled();
    const pending = deferred<PersonalPolicy>();
    vi.mocked(api.replacePolicy).mockReturnValueOnce(pending.promise);
    const operation = state.confirm();
    expect(state.form.secret).toBe('');
    expect(state.busy).toBe(true);
    expect(api.replacePolicy).toHaveBeenCalledWith('personal', { expected_revision: 'r1', settings: { requested_scopes: ['A', 'z'], client: { kind: 'preconfigured_confidential', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'app', client_secret: 'secret-sentinel', token_endpoint_auth_method: 'client_secret_post' } } });
    await state.confirm();
    expect(api.replacePolicy).toHaveBeenCalledTimes(1);
    pending.resolve(policyFixture());
    await operation;
    expect(state.form.secret).toBe('');
  });
  test.each(['close', 'switch', 'dispose'] as const)('clears confidential secret on %s', async (action) => {
    const { state } = setup();
    await state.reload();
    confidential(state);
    if (action === 'close') state.close();
    if (action === 'switch') state.form.setKind('preconfigured_public');
    if (action === 'dispose') state.dispose();
    expect(state.form.secret).toBe('');
  });
  test('confidential read never prefills a secret and every save requires fresh input', async () => {
    const { api, state } = setup();
    vi.mocked(api.policy).mockResolvedValue({ ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true } });
    await state.reload();
    expect(state.form.configured).toBe(true);
    expect(state.form.secret).toBe('');
    state.requestConfirmation('policy');
    await state.confirm();
    expect(api.replacePolicy).not.toHaveBeenCalled();
    expect(state.message).toContain('fresh secret');
    expect(state.blocked).toBe(false);
  });
  test.each([
    new HttpError(409, 'secret-sentinel', { detail: { code: 'personal_oauth_configuration_conflict', message: 'secret-sentinel' } }),
    new NetworkError(new Error('secret-sentinel')),
    new SchemaValidationError('inbound', []),
    new SyntaxError('secret-sentinel'),
    new HttpError(503, 'secret-sentinel', {})
  ])('conflict or uncertain write requires manual authoritative reload without replay', async (error) => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    vi.mocked(api.replacePolicy).mockRejectedValueOnce(error);
    state.requestConfirmation('policy');
    await state.confirm();
    expect(state.blocked).toBe(true);
    expect(state.message).not.toContain('secret-sentinel');
    expect(state.message).toMatch(/Reload/);
    expect(state.form.secret).toBe('');
    expect(api.list).toHaveBeenCalledTimes(1);
    state.requestConfirmation('publish');
    await state.confirm();
    expect(api.publish).not.toHaveBeenCalled();
    expect(api.replacePolicy).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.blocked).toBe(false);
    expect(api.replacePolicy).toHaveBeenCalledTimes(1);
  });
  test('a definite rejection can be explicitly corrected and never retains a secret', async () => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    vi.mocked(api.replacePolicy).mockRejectedValueOnce(new HttpError(422, 'secret-sentinel', { submitted: 'secret-sentinel' }));
    state.requestConfirmation('policy');
    await state.confirm();
    expect(state.blocked).toBe(false);
    expect(state.message).not.toContain('secret-sentinel');
    expect(state.form.secret).toBe('');
    state.form.set('secret', 'fresh');
    state.requestConfirmation('policy');
    await state.confirm();
    expect(api.replacePolicy).toHaveBeenCalledTimes(2);
  });
  test('invalid scope text fails before I/O and clears entered secret', async () => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    state.form.set('scopes', 'read\u00a0write');
    state.requestConfirmation('policy');
    await state.confirm();
    expect(api.replacePolicy).not.toHaveBeenCalled();
    expect(state.form.secret).toBe('');
  });
  test('publication and withdrawal require confirmation, independent of empty tool inventory', async () => {
    const { api, state } = setup();
    await state.reload();
    state.requestConfirmation('publish');
    expect(api.publish).not.toHaveBeenCalled();
    await state.confirm();
    expect(state.selected?.publication_status).toBe('published');
    expect(api.publish).toHaveBeenCalledTimes(1);
    state.requestConfirmation('withdraw');
    expect(api.withdraw).not.toHaveBeenCalled();
    await state.confirm();
    expect(state.selected?.publication_status).toBe('unpublished');
  });
  test('grant-blocked deletion explains recovery with no retry', async () => {
    const { api, state } = setup();
    await state.reload();
    vi.mocked(api.delete).mockRejectedValueOnce(new HttpError(409, '', { detail: { code: 'downstream_connector_grants_conflict' } }));
    state.requestConfirmation('delete');
    expect(api.delete).not.toHaveBeenCalled();
    await state.confirm();
    expect(state.message).toContain('Remove connector and tool grants');
    expect(state.selected).not.toBeNull();
    expect(api.delete).toHaveBeenCalledTimes(1);
  });
  test('unsupported deployment is reported with operator guidance', async () => {
    const { api, state } = setup();
    vi.mocked(api.policy).mockRejectedValueOnce(new HttpError(404, '', { detail: { code: 'personal_connections_unavailable' } }));
    await state.reload();
    expect(state.unavailable).toBe(true);
    expect(state.locked).toBe(true);
    expect(state.message).toContain('unavailable in this deployment');
    expect(state.message).toContain('stable identity namespace');
    expect(state.availability.registration).toBe('disabled');
  });
  test('selection changes suppress late selected policy responses', async () => {
    const { api, state } = setup();
    vi.mocked(api.list).mockResolvedValue([summaryFixture(), summaryFixture('other')]);
    vi.mocked(api.get).mockImplementation(async (id) => serverFixture(id));
    const old = deferred<PersonalPolicy>();
    vi.mocked(api.policy).mockImplementation((id) => id === 'personal' ? old.promise : Promise.resolve(policyFixture(id)));
    const first = state.reload('personal');
    await vi.waitFor(() => expect(api.policy).toHaveBeenCalledWith('personal'));
    await state.select('other');
    old.resolve(policyFixture());
    await first;
    expect(state.selectedId).toBe('other');
    expect(state.selected?.connector_id).toBe('other');
    expect(state.policy?.connector_id).toBe('other');
  });
  test.each(['read', 'write'] as const)('disposal suppresses late %s responses and clears forms', async (mode) => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    const pending = deferred<PersonalPolicy>();
    let operation: Promise<void>;
    if (mode === 'read') { vi.mocked(api.policy).mockReturnValueOnce(pending.promise); operation = state.reload(); }
    else { vi.mocked(api.replacePolicy).mockReturnValueOnce(pending.promise); state.requestConfirmation('policy'); operation = state.confirm(); }
    await Promise.resolve();
    state.dispose();
    pending.resolve(policyFixture());
    await operation;
    expect(state.records).toEqual([]);
    expect(state.selected).toBeNull();
    expect(state.policy).toBeNull();
    expect(state.form.secret).toBe('');
    expect(state.metadata.name).toBe('');
  });
  test.each(['read', 'write'] as const)('authentication loss during %s clears everything without redirect or replay', async (mode) => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    if (mode === 'read') { vi.mocked(api.policy).mockRejectedValueOnce(new AuthenticationRequiredError()); await state.reload(); }
    else { vi.mocked(api.replacePolicy).mockRejectedValueOnce(new AuthenticationRequiredError()); state.requestConfirmation('policy'); await state.confirm(); }
    expect(state.authenticationLost).toBe(true);
    expect(state.records).toEqual([]);
    expect(state.selected).toBeNull();
    expect(state.policy).toBeNull();
    expect(state.form.secret).toBe('');
    expect(state.locked).toBe(true);
    state.openCreate();
    expect(state.creating).toBe(false);
  });
  test('busy mutation rejects competing operations and preserves submitted identity', async () => {
    const { api, state } = setup();
    await state.reload();
    const pending = deferred<{ connector_id: string; publication_status: 'published' }>();
    vi.mocked(api.publish).mockReturnValueOnce(pending.promise);
    state.requestConfirmation('publish');
    const operation = state.confirm();
    state.openCreate();
    state.close();
    await state.select('other');
    await state.reload();
    state.requestConfirmation('delete');
    await state.confirm();
    expect(api.list).toHaveBeenCalledTimes(1);
    expect(api.delete).not.toHaveBeenCalled();
    expect(state.creating).toBe(false);
    expect(state.selectedId).toBe('personal');
    pending.resolve({ connector_id: 'personal', publication_status: 'published' });
    await operation;
  });
});
