import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import PersonalOAuthSetupDialog from './PersonalOAuthSetupDialog.svelte';
import { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';
import { InMemoryPersonalOAuthSetup, discoveryFixture, setupFixture } from '#lib/admin/personal-mcp-servers/setup.test-support.js';
import { InMemoryPersonalServers } from '#lib/admin/personal-mcp-servers/in-memory.js';
import { policyFixture, serverFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { HttpError, NetworkError } from '#lib/admin/infrastructure/transport.js';
import type { SetupStatus } from '#lib/admin/personal-mcp-servers/domain/setup.js';
import type { PersonalPolicy } from '#lib/admin/personal-mcp-servers/domain/schemas.js';

let component: ReturnType<typeof mount> | undefined;
let ownedState: PersonalOAuthSetupState | undefined;

afterEach(async (): Promise<void> => {
  ownedState?.dispose();
  ownedState = undefined;
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function findButton(label: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
}

function button(label: string): HTMLButtonElement {
  const element = findButton(label);
  if (!element) throw new Error(`Button not found: ${label}`);
  return element;
}

async function openDialog(setup: InMemoryPersonalOAuthSetup = new InMemoryPersonalOAuthSetup(), policy: PersonalPolicy = policyFixture(), published = false): Promise<{ servers: InMemoryPersonalServers; validationChanged: ReturnType<typeof vi.fn>; close: ReturnType<typeof vi.fn>; edit: ReturnType<typeof vi.fn>; publish: ReturnType<typeof vi.fn> }> {
  const servers = new InMemoryPersonalServers([serverFixture()], [policy]);
  setup.bindPolicies(servers);
  const validationChanged = vi.fn();
  const close = vi.fn();
  const edit = vi.fn();
  const publish = vi.fn();
  const state = new PersonalOAuthSetupState(setup, servers, validationChanged, vi.fn(), vi.fn(), vi.fn());
  const target = document.createElement('div');
  document.body.append(target);
  ownedState = state;
  await state.load('personal');
  component = mount(PersonalOAuthSetupDialog, { target, props: { state, close, edit, publish, published } });
  flushSync();
  return { servers, validationChanged, close, edit, publish };
}

describe('administrator configuration check', (): void => {
  test('unchecked configuration offers only the required check, without an editor or technical report', async (): Promise<void> => {
    await openDialog();
    expect(document.body.textContent).toContain('Check required');
    expect(button('Check configuration').disabled).toBe(false);
    expect(findButton('Edit settings')).toBeUndefined();
    expect(document.querySelectorAll('input, details, code')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('Sign-in not tested');
    expect(document.body.textContent).not.toContain('register a public OAuth application');
  });

  test('successful check ends with clear readiness and publication, not more configuration work', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const { servers, validationChanged, publish } = await openDialog(setup);
    const replace = vi.spyOn(servers, 'replacePolicy');
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ready to publish'));
    expect(validationChanged).toHaveBeenLastCalledWith('personal', true);
    expect(document.querySelectorAll('input, details, code, time')).toHaveLength(0);
    expect(findButton('Check configuration')).toBeUndefined();
    expect(findButton('Check again')).toBeUndefined();
    expect(findButton('Edit settings')).toBeUndefined();
    expect(document.body.textContent).not.toContain('Approve');
    expect(document.body.textContent).not.toContain('not verified');
    expect(replace).not.toHaveBeenCalled();
    expect(publish).not.toHaveBeenCalled();
    button('Publish').click();
    expect(publish).toHaveBeenCalledOnce();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });

  test('a published server with a current check needs no further action', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.current = setup.validation;
    const { close } = await openDialog(setup, policyFixture(), true);
    expect(document.body.textContent).toContain('Configuration ready');
    expect(findButton('Publish')).toBeUndefined();
    expect(findButton('Check configuration')).toBeUndefined();
    expect(findButton('Edit settings')).toBeUndefined();
    button('Done').click();
    expect(close).toHaveBeenCalledOnce();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
  });

  test('scope mismatch shows only corrective permissions and never writes or silently approves settings', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: ['records:write'], downstream_response: { kind: 'http_response', status_code: 201 } } });
    const { servers, edit, validationChanged } = await openDialog(setup, { ...policyFixture(), requested_scopes: ['records:read'] });
    const replace = vi.spyOn(servers, 'replacePolicy');
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Changes required'));
    expect(document.body.textContent).toContain('Requested permissionsrecords:read');
    expect(document.body.textContent).toContain('Provider returnedrecords:write');
    expect(document.querySelectorAll('input, details')).toHaveLength(0);
    expect(document.body.textContent).not.toContain('Approve');
    expect(findButton('Publish')).toBeUndefined();
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
    const trigger = button('Edit settings');
    trigger.click();
    expect(edit).toHaveBeenCalledExactlyOnceWith(trigger);
    expect(replace).not.toHaveBeenCalled();
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
  });

  test('issuer mismatch directs the administrator to edit without accepting a provider automatically', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'issuer_mismatch' });
    const { servers, edit } = await openDialog(setup, { ...policyFixture(), client: { kind: 'preconfigured_public', issuer_url: 'https://configured.test', client_id: 'app' } });
    const replace = vi.spyOn(servers, 'replacePolicy');
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Required authorization provider'));
    expect(document.body.textContent).toContain('https://issuer.test');
    expect(document.body.textContent).toContain('Changes required');
    expect(findButton('Accept discovered issuer')).toBeUndefined();
    button('Edit settings').click();
    expect(edit).toHaveBeenCalledOnce();
    expect(replace).not.toHaveBeenCalled();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation', 'discovery']);
  });

  test.each(['dynamic_public', 'dynamic_confidential'] as const)('%s readiness explains metadata-only validation and later independent user sign-in', async (kind): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'validated', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'validated', discovery: { ...discoveryFixture(), registration_mode: kind }, returned_scopes: [], scope_source: 'not_checked' } });
    const client: PersonalPolicy['client'] = kind === 'dynamic_public' ? { kind } : { kind, token_endpoint_auth_method: 'client_secret_basic' };
    await openDialog(setup, { ...policyFixture(), client });
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ready to publish'));
    expect(document.body.textContent).toContain('Only provider metadata was checked.');
    expect(document.body.textContent).toContain('Automatic application registration and each user’s sign-in happen when they connect');
    expect(document.body.textContent).toContain('this check does not prove either will succeed');
    expect(document.body.textContent).not.toContain('Confirm them and this callback URL');
    expect(document.querySelectorAll('input')).toHaveLength(0);
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });
  test.each(['preconfigured_public', 'preconfigured_confidential'] as const)('existing %s clients retain only the essential provider-side credential and callback reminder', async (kind): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const effective = 'https://umbod.test/oauth/callback/issuer/hashed-issuer';
    setup.validation = setupFixture({ status: 'validated', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'validated', discovery: { ...discoveryFixture(), registration_mode: kind, redirect_uri: effective }, returned_scopes: [], scope_source: 'not_checked' } });
    const client: PersonalPolicy['client'] = kind === 'preconfigured_public'
      ? { kind, issuer_url: 'https://issuer.test', client_id: 'app' }
      : { kind, issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true };
    await openDialog(setup, { ...policyFixture(), client });
    expect(document.querySelector('code')).toBeNull();
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Ready to publish'));
    expect(document.body.textContent).toContain('Client credentials are not tested');
    expect(document.body.textContent).not.toContain('Automatic application registration');
    expect(document.querySelector('code')?.textContent).toBe(effective);
    expect(document.body.textContent).not.toContain('Unvalidated redirect URI');
    expect(document.querySelectorAll('input, details')).toHaveLength(0);
  });

  test.each(['timeout', 'network_failure'] as const)('temporary %s failure offers a deliberate retry rather than unnecessary editing', async (reason): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason });
    await openDialog(setup);
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Check failed'));
    expect(findButton('Edit settings')).toBeUndefined();
    expect(button('Check again').disabled).toBe(false);
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(1);
    button('Check again').click();
    await vi.waitFor(() => expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(2));
  });

  test('unsupported automatic registration makes editing the necessary next action', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'failed', checked_at: '2026-01-01T00:00:00Z', stage: 'discovery', reason: 'registration_unavailable' });
    await openDialog(setup);
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Changes required'));
    expect(button('Edit settings').disabled).toBe(false);
    expect(findButton('Publish')).toBeUndefined();
    expect(document.querySelectorAll('input, details')).toHaveLength(0);
  });

  test('an unknown outcome requires refreshing status and never exposes a registration retry', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    vi.spyOn(setup, 'validate').mockRejectedValueOnce(new NetworkError(new Error('provider-secret')));
    await openDialog(setup);
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Check result unavailable'));
    expect(document.body.textContent).not.toContain('provider-secret');
    expect(findButton('Check again')).toBeUndefined();
    expect(findButton('Check configuration')).toBeUndefined();
    expect(findButton('Edit settings')).toBeUndefined();
    expect(button('Refresh status').disabled).toBe(false);
    button('Refresh status').click();
    await vi.waitFor(() => expect(button('Check configuration').disabled).toBe(false));
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(0);
    expect(setup.calls.filter((call) => call.operation === 'status')).toHaveLength(2);
  });

  test('a saved in-progress check allows status refresh only', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.current = setupFixture({ status: 'in_progress', operation: 'validation', attempt_id: 'attempt', lease_expires_at: '2026-01-01T00:01:00Z' });
    await openDialog(setup);
    expect(button('Refresh status').disabled).toBe(false);
    expect(findButton('Check configuration')).toBeUndefined();
    expect(findButton('Check again')).toBeUndefined();
    expect(setup.calls.map((call) => call.operation)).toEqual(['status']);
  });

  test('lost administration access leaves only dismissal and safe sign-in guidance', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    vi.spyOn(setup, 'validate').mockRejectedValueOnce(new HttpError(403, '', { detail: 'provider-secret' }));
    await openDialog(setup);
    button('Check configuration').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Admin access required'));
    expect(document.body.textContent).not.toContain('provider-secret');
    expect(document.querySelectorAll('input, details')).toHaveLength(0);
    expect(findButton('Check configuration')).toBeUndefined();
    expect(findButton('Edit settings')).toBeUndefined();
    expect(findButton('Refresh status')).toBeUndefined();
    expect(button('Close').disabled).toBe(false);
  });

  test('pending check blocks duplicate actions and survives closing its rendering owner', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    let resolve!: (status: SetupStatus) => void;
    const pending = new Promise<SetupStatus>((accept) => { resolve = accept; });
    const validate = vi.spyOn(setup, 'validate').mockReturnValueOnce(pending);
    const { validationChanged } = await openDialog(setup);
    button('Check configuration').click();
    await tick();
    expect(document.body.textContent).toContain('Checking configuration');
    expect(button('Check configuration').disabled).toBe(true);
    expect(button('Close').disabled).toBe(true);
    button('Check configuration').click();
    expect(validate).toHaveBeenCalledOnce();
    if (!component) throw new Error('Dialog was not mounted');
    await unmount(component);
    component = undefined;
    resolve(setup.validation);
    await pending;
    await tick();
    expect(validationChanged).toHaveBeenLastCalledWith('personal', true);
  });
});
