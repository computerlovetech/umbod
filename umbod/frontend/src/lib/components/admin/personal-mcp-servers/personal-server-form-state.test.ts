import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError, NetworkError, SchemaValidationError } from '$lib/admin/infrastructure/transport';
import type { PersonalServerAdministration } from '$lib/admin/personal-mcp-servers/administration';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import type { PersonalPolicy } from '$lib/admin/personal-mcp-servers/domain/schemas';
import { DownstreamMcpWorkspaceState } from '../downstream-mcp-connectors/downstream-mcp-workspace-state.svelte';
import { PersonalServerFormState } from './personal-server-form-state.svelte';
import type { InstanceConfigurationRoute } from '$lib/admin/instance-configuration-api';
import type { InstanceConfiguration } from '$lib/admin/instance-configuration';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';

function setup(targetId: string | null = 'personal', lockChanged: (locked: boolean) => void = () => {}): { api: PersonalServerAdministration; configuration: InstanceConfigurationRoute; state: PersonalServerFormState; completed: ReturnType<typeof vi.fn>; lost: ReturnType<typeof vi.fn> } {
  const memory: PersonalServerAdministration = new InMemoryPersonalServers([serverFixture()], [policyFixture()]);
  const api: PersonalServerAdministration = {
    get: vi.fn((id) => memory.get(id)), policy: vi.fn((id) => memory.policy(id)), create: vi.fn((input) => memory.create(input)), replacePolicy: vi.fn((id, input) => memory.replacePolicy(id, input))
  };
  const configuration: InstanceConfigurationRoute = { get: vi.fn(async () => configurationFixture()) };
  const completed = vi.fn(async () => {});
  const lost = vi.fn();
  return { api, configuration, state: new PersonalServerFormState(api, configuration, targetId, completed, lost, lockChanged), completed, lost };
}
function confidential(state: PersonalServerFormState): void {
  state.form.setKind('preconfigured_confidential');
  state.form.set('issuer', 'https://Issuer.test:443/Exact/');
  state.form.set('clientId', 'app');
  state.form.set('secret', 'secret-sentinel');
}
function metadata(state: PersonalServerFormState): void {
  for (const [field, value] of Object.entries({ name: 'New server', prefix: 'new', description: 'Search records', path: 'new', endpoint: 'https://provider.test/mcp' })) state.setMetadata(field as keyof typeof state.metadata, value);
}
function deferred<T>(): { promise: Promise<T>; resolve: (value: T) => void; reject: (error: unknown) => void } {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

describe('personal registration and selected policy through administration port', () => {
  test('unknown registration remains a workspace-wide mutation gate after close and independent policy disposal', async () => {
    const workspace = new DownstreamMcpWorkspaceState();
    const { api, state } = setup(null, workspace.operations.setRegistrationLocked);
    await state.reload();
    state.openCreate();
    metadata(state);
    confidential(state);
    vi.mocked(api.create).mockRejectedValueOnce(new NetworkError(new Error('lost-response')));
    await state.create();
    state.close();
    expect(state.form.secret).toBe('');
    expect(state.creating).toBe(false);
    expect(workspace.operations.registrationLocked).toBe(true);
    workspace.operations.setFormLocked(true);
    workspace.operations.setFormLocked(false);
    expect(workspace.operations.locked).toBe(true);
    workspace.operations.request('publish', 'personal', 'Personal');
    expect(workspace.operations.pending).toBeNull();
    workspace.operations.request('delete', 'personal', 'Personal');
    expect(workspace.operations.pending).toBeNull();
    workspace.open('create', { focus() {} } as HTMLElement);
    expect(workspace.modal).toBeNull();
    workspace.openCapabilityDescription('shared', { focus() {} } as HTMLElement);
    expect(workspace.capabilityDescriptionConnectorId).toBeNull();
    const form = { requestSubmit: vi.fn() } as unknown as HTMLFormElement;
    workspace.requestPublicationConfirmation(form, 'Shared', 'Publish');
    workspace.confirmPublication();
    expect(form.requestSubmit).not.toHaveBeenCalled();
    await state.reload();
    expect(workspace.operations.locked).toBe(true);
    expect(api.create).toHaveBeenCalledTimes(1);
  });
  test('registration reconciliation callback stays locked while pending and after failure', async () => {
    const workspace = new DownstreamMcpWorkspaceState();
    const { state, completed } = setup(null, workspace.operations.setRegistrationLocked);
    await state.reload();
    state.openCreate();
    metadata(state);
    const reconciliation = deferred<void>();
    completed.mockReturnValueOnce(reconciliation.promise);
    const operation = state.create();
    await vi.waitFor(() => expect(completed).toHaveBeenCalledOnce());
    expect(state.busy).toBe(true);
    expect(workspace.operations.registrationLocked).toBe(true);
    reconciliation.reject(new Error('navigation-failed'));
    await operation;
    expect(state.busy).toBe(false);
    expect(state.blocked).toBe(true);
    expect(workspace.operations.registrationLocked).toBe(true);
    workspace.operations.setFormLocked(false);
    expect(workspace.operations.locked).toBe(true);
  });
  test('registration fails closed until authoritative startup configuration resolves without loading an inventory', async () => {
    const { api, configuration, state } = setup(null);
    const pending = deferred<InstanceConfiguration>();
    vi.mocked(configuration.get).mockReturnValueOnce(pending.promise);
    state.openCreate();
    expect(state.creating).toBe(false);
    const operation = state.reload();
    await state.create();
    expect(api.create).not.toHaveBeenCalled();
    pending.resolve(configurationFixture());
    await operation;
    expect(state.canRegister).toBe(true);
    for (const read of [api.get, api.policy]) expect(read).not.toHaveBeenCalled();
  });
  test.each(['disabled', 'missing', 'mistyped', 'failed'] as const)('%s availability blocks personal registration', async (mode) => {
    const { api, configuration, state } = setup(null);
    const result = configurationFixture(false);
    if (mode === 'missing') result.groups = [];
    if (mode === 'mistyped') result.groups[0].entries[0] = { ...result.groups[0].entries[0], type: 'string', value: 'true' };
    if (mode === 'failed') vi.mocked(configuration.get).mockRejectedValueOnce(new Error('secret-sentinel'));
    else vi.mocked(configuration.get).mockResolvedValueOnce(result);
    await state.reload();
    expect(state.canRegister).toBe(false);
    state.openCreate();
    await state.create();
    expect(api.create).not.toHaveBeenCalled();
    expect(state.message).not.toContain('secret-sentinel');
  });
  test('explicit reload recovers unknown availability and OAuth-disabled registration remains allowed', async () => {
    const { configuration, state } = setup(null);
    vi.mocked(configuration.get).mockRejectedValueOnce(new Error('secret-sentinel'));
    await state.reload();
    expect(state.availability.registration).toBe('unknown');
    vi.mocked(configuration.get).mockResolvedValueOnce(configurationFixture(true, false));
    await state.reload();
    expect(state.canRegister).toBe(true);
    expect(state.availability.authorization).toBe('disabled');
  });
  test('registration reports the new unpublished ID to the one inventory without provider or grant actions', async () => {
    const { api, state, completed } = setup(null);
    await state.reload();
    state.openCreate();
    metadata(state);
    await state.create();
    expect(api.create).toHaveBeenCalledTimes(1);
    expect(completed).toHaveBeenCalledWith('new');
    expect(state.creating).toBe(false);
    for (const operation of [api.policy, api.replacePolicy]) expect(operation).not.toHaveBeenCalled();
  });
  test.each(['personal_connections_unavailable', 'proxy_not_found'] as const)('registration 404 %s requires explicit reconciliation', async (code) => {
    const { api, state } = setup(null);
    await state.reload();
    state.openCreate();
    metadata(state);
    confidential(state);
    vi.mocked(api.create).mockRejectedValueOnce(new HttpError(404, 'secret-sentinel', { detail: { code } }));
    await state.create();
    expect(state.canRegister).toBe(false);
    expect(state.form.secret).toBe('');
    expect(state.message).not.toContain('secret-sentinel');
    await state.create();
    expect(api.create).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.canRegister).toBe(false);
    expect(state.blocked).toBe(true);
  });
  test('uncertain registration stays locked through cancel and reopen until explicit reload', async () => {
    const { api, state } = setup(null);
    await state.reload();
    state.openCreate();
    metadata(state);
    confidential(state);
    vi.mocked(api.create).mockRejectedValueOnce(new NetworkError(new Error('secret-sentinel')));
    await state.create();
    state.close();
    state.openCreate();
    await state.create();
    expect(state.blocked).toBe(true);
    expect(state.form.secret).toBe('');
    expect(api.create).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.blocked).toBe(true);
    expect(state.canRegister).toBe(false);
    expect(api.create).toHaveBeenCalledTimes(1);
  });
  test('selected policy reads only its fixed definition and policy, never an inventory', async () => {
    const { api, configuration, state } = setup();
    await state.reload();
    expect(configuration.get).not.toHaveBeenCalled();
    expect(api.get).toHaveBeenCalledWith('personal');
    expect(api.policy).toHaveBeenCalledWith('personal');
    expect(state.policy?.revision).toBe('r1');
  });
  test('explicit confirmation precedes one revision-checked replacement and clears secrets immediately', async () => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    state.form.set('scopes', 'z A');
    state.form.setMethod('client_secret_post');
    state.requestConfirmation('policy');
    expect(api.replacePolicy).not.toHaveBeenCalled();
    const pending = deferred<PersonalPolicy>();
    vi.mocked(api.replacePolicy).mockReturnValueOnce(pending.promise);
    const operation = state.confirm();
    expect(state.form.secret).toBe('');
    expect(api.replacePolicy).toHaveBeenCalledWith('personal', { expected_revision: 'r1', settings: { requested_scopes: ['A', 'z'], client: { kind: 'preconfigured_confidential', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'app', client_secret: 'secret-sentinel', token_endpoint_auth_method: 'client_secret_post' } } });
    state.close();
    await state.reload();
    await state.confirm();
    expect(api.replacePolicy).toHaveBeenCalledTimes(1);
    pending.resolve(policyFixture());
    await operation;
    expect(state.form.secret).toBe('');
  });
  test.each(['close', 'switch', 'dispose'] as const)('clears confidential secrets on %s', async (action) => {
    const { state } = setup();
    await state.reload();
    confidential(state);
    if (action === 'close') state.close();
    if (action === 'switch') state.form.setKind('preconfigured_public');
    if (action === 'dispose') state.dispose();
    expect(state.form.secret).toBe('');
  });
  test('confidential reads never prefill secrets and saving requires a fresh secret', async () => {
    const { api, state } = setup();
    vi.mocked(api.policy).mockResolvedValue({ ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true } });
    await state.reload();
    expect(state.form.configured).toBe(true);
    expect(state.form.secret).toBe('');
    state.requestConfirmation('policy');
    await state.confirm();
    expect(api.replacePolicy).not.toHaveBeenCalled();
    expect(state.message).toContain('fresh secret');
  });
  test.each([new HttpError(409, '', { detail: { code: 'personal_oauth_configuration_conflict' } }), new NetworkError(new Error('secret-sentinel')), new SchemaValidationError('inbound', []), new SyntaxError('secret-sentinel'), new HttpError(503, '', {})])('conflict and uncertain policy writes remain locked until authoritative reload', async (error) => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    vi.mocked(api.replacePolicy).mockRejectedValueOnce(error);
    state.requestConfirmation('policy');
    await state.confirm();
    expect(state.blocked).toBe(true);
    expect(state.message).not.toContain('secret-sentinel');
    expect(state.form.secret).toBe('');
    state.requestConfirmation('policy');
    await state.confirm();
    expect(api.replacePolicy).toHaveBeenCalledTimes(1);
    await state.reload();
    expect(state.blocked).toBe(false);
  });
  test.each(['invalid-scope', 'rejected'] as const)('definite %s failure clears secrets without automatic replay', async (mode) => {
    const { api, state } = setup();
    await state.reload();
    confidential(state);
    if (mode === 'invalid-scope') state.form.set('scopes', 'read\u00a0write');
    else vi.mocked(api.replacePolicy).mockRejectedValueOnce(new HttpError(422, 'secret-sentinel', null));
    state.requestConfirmation('policy');
    await state.confirm();
    expect(state.form.secret).toBe('');
    expect(state.blocked).toBe(false);
    expect(state.message).not.toContain('secret-sentinel');
    expect(api.replacePolicy).toHaveBeenCalledTimes(mode === 'invalid-scope' ? 0 : 1);
  });
  test.each(['read', 'write'] as const)('disposal fences late %s responses when the workspace selects another server', async (mode) => {
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
    expect(state.selected).toBeNull();
    expect(state.policy).toBeNull();
    expect(state.form.secret).toBe('');
  });
  test.each(['configuration', 'read', 'write'] as const)('authentication loss during %s clears forms and notifies the workspace without retry', async (mode) => {
    const { api, configuration, state, lost } = setup(mode === 'configuration' ? null : 'personal');
    await state.reload();
    confidential(state);
    if (mode === 'configuration') { vi.mocked(configuration.get).mockRejectedValueOnce(new AuthenticationRequiredError()); await state.reload(); }
    else if (mode === 'read') { vi.mocked(api.policy).mockRejectedValueOnce(new AuthenticationRequiredError()); await state.reload(); }
    else { vi.mocked(api.replacePolicy).mockRejectedValueOnce(new AuthenticationRequiredError()); state.requestConfirmation('policy'); await state.confirm(); }
    expect(state.authenticationLost).toBe(true);
    expect(lost).toHaveBeenCalledTimes(1);
    expect(state.selected).toBeNull();
    expect(state.policy).toBeNull();
    expect(state.form.secret).toBe('');
    expect(state.locked).toBe(true);
    await state.reload();
    expect(lost).toHaveBeenCalledTimes(1);
  });
});
