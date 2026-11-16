import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import PersonalOAuthSetupPanel from './PersonalOAuthSetupPanel.svelte';
import { PersonalOAuthSetupState } from './personal-oauth-setup-state.svelte';
import { InMemoryPersonalOAuthSetup, discoveryFixture, setupFixture } from '$lib/admin/personal-mcp-servers/setup.test-support';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture, serverFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { HttpError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { SetupStatus } from '$lib/admin/personal-mcp-servers/domain/setup';
import type { PersonalPolicy } from '$lib/admin/personal-mcp-servers/domain/schemas';

let component: ReturnType<typeof mount> | undefined;

afterEach(async (): Promise<void> => {
  if (component) await unmount(component);
  component = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string): HTMLButtonElement {
  const element = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  if (!element) throw new Error(`Button not found: ${label}`);
  return element;
}

async function openPanel(setup: InMemoryPersonalOAuthSetup = new InMemoryPersonalOAuthSetup(), policy: PersonalPolicy = policyFixture()): Promise<{ servers: InMemoryPersonalServers; validationChanged: ReturnType<typeof vi.fn> }> {
  const servers = new InMemoryPersonalServers([serverFixture()], [policy]);
  setup.bindPolicies(servers);
  const validationChanged = vi.fn();
  const state = new PersonalOAuthSetupState(setup, servers, validationChanged, vi.fn(), vi.fn(), vi.fn());
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(PersonalOAuthSetupPanel, { target, props: { state, connectorId: 'personal' } });
  flushSync();
  await vi.waitFor(() => expect(button('Validate setup').disabled).toBe(false));
  return { servers, validationChanged };
}

describe('personal OAuth setup interactions', (): void => {
  test('discovery candidates start unchecked and only explicit approval writes policy', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const { servers } = await openPanel(setup);
    const replace = vi.spyOn(servers, 'replacePolicy');
    expect(document.querySelectorAll('input')).toHaveLength(0);
    button('Discover settings').click();
    await vi.waitFor(() => expect(document.querySelectorAll('input[type="checkbox"]')).toHaveLength(2));
    const candidates = [...document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')];
    expect(candidates.every((candidate) => !candidate.checked)).toBe(true);
    expect(replace).not.toHaveBeenCalled();
    expect(button('Approve selected scopes').disabled).toBe(true);
    candidates[0].click();
    await tick();
    expect(replace).not.toHaveBeenCalled();
    button('Approve selected scopes').click();
    await vi.waitFor(() => expect(replace).toHaveBeenCalledOnce());
    expect((await servers.policy('personal')).requested_scopes).toEqual(['records:read']);
    await vi.waitFor(() => expect(document.body.textContent).toContain('Validate setup again'));
    expect(setup.calls.filter((call) => call.operation === 'validation')).toHaveLength(0);
  });

  test('mismatch separates configured and provider scopes and never treats registration as personal login', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'scope_mismatch', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'scope_mismatch', discovery: discoveryFixture(), returned_scopes: ['records:write'], downstream_response: { kind: 'http_response', status_code: 201 } } });
    const { servers, validationChanged } = await openPanel(setup);
    const replace = vi.spyOn(servers, 'replacePolicy');
    button('Validate setup').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('The provider returned different scopes'));
    expect(document.body.textContent).toContain('Configured scopes: (none explicitly requested)');
    expect(document.body.textContent).toContain('Provider scopes: records:write');
    expect(document.body.textContent).toContain('Sign-in not tested');
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.querySelector('a')).toBeNull();
    expect(replace).not.toHaveBeenCalled();
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
    button('Approve provider scopes').click();
    await vi.waitFor(() => expect(replace).toHaveBeenCalledOnce());
    expect((await servers.policy('personal')).requested_scopes).toEqual(['records:write']);
  });

  test('successful configuration validation changes publication eligibility but sign-in remains untested', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const { validationChanged } = await openPanel(setup);
    expect(document.body.textContent).toContain('Configuration not validated');
    button('Validate setup').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Configuration validated'));
    expect(document.body.textContent).toContain('Sign-in not tested');
    expect(validationChanged).toHaveBeenLastCalledWith('personal', true);
    expect(document.body.textContent).not.toContain('Sign in to validate');
    expect(setup.calls.map((call) => call.operation)).toEqual(['status', 'validation']);
  });

  test('static setup validation never claims credentials or sign-in were verified', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    setup.validation = setupFixture({ status: 'validated', checked_at: '2026-01-01T00:00:00Z', result: { kind: 'validated', discovery: { ...discoveryFixture(), registration_mode: 'preconfigured_confidential' }, returned_scopes: [], scope_source: 'not_checked' } });
    await openPanel(setup, { ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_basic', client_secret_configured: true } });
    button('Validate setup').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Configuration validated'));
    expect(document.body.textContent).toContain('Static client credentials are not verified');
    expect(document.body.textContent).toContain('Sign-in not tested');
    expect(document.querySelector('input[type="password"]')).toBeNull();
    expect(document.body.textContent).not.toContain('register a public OAuth application');
  });

  test('issuer-bound discovery displays the exact effective redirect URI instead of the unvalidated base', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const effective = 'https://umbod.test/oauth/callback/issuer/hashed-issuer';
    setup.discovery = setupFixture({ status: 'discovered', checked_at: '2026-01-01T00:00:00Z', discovery: { ...discoveryFixture(), redirect_uri: effective } });
    await openPanel(setup, { ...policyFixture(), client: { kind: 'preconfigured_public', issuer_url: 'https://issuer.test', client_id: 'app' } });
    expect(document.body.textContent).toContain('Unvalidated redirect URI: https://umbod.test/oauth/callback');
    button('Discover settings').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain(`Effective redirect URI: ${effective}`));
    expect(document.body.textContent).not.toContain('Unvalidated redirect URI:');
    const redirect = [...document.querySelectorAll('p')].find((paragraph) => paragraph.textContent?.startsWith('Effective redirect URI:'));
    expect(redirect?.querySelector('code')?.textContent).toBe(effective);
  });

  test('discovered issuer is accepted only through an explicit revision-safe save', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    const { servers } = await openPanel(setup, { ...policyFixture(), client: { kind: 'preconfigured_public', issuer_url: 'https://configured.test', client_id: 'app' } });
    const replace = vi.spyOn(servers, 'replacePolicy');
    button('Discover settings').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('Configured issuer: https://configured.test'));
    expect(replace).not.toHaveBeenCalled();
    button('Accept discovered issuer').click();
    await vi.waitFor(() => expect(document.body.textContent).toContain('OAuth settings saved'));
    expect(replace).toHaveBeenCalledExactlyOnceWith('personal', { expected_revision: 'r1', settings: { requested_scopes: [], client: { kind: 'preconfigured_public', issuer_url: 'https://issuer.test', client_id: 'app' } } });
  });

  test('pending registration disables duplicate interactions and unmount fences its result', async (): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    let resolve!: (status: SetupStatus) => void;
    const pending = new Promise<SetupStatus>((accept) => { resolve = accept; });
    const validate = vi.spyOn(setup, 'validate').mockReturnValueOnce(pending);
    const { validationChanged } = await openPanel(setup);
    button('Validate setup').click();
    await tick();
    expect(button('Validate setup').disabled).toBe(true);
    expect(button('Discover settings').disabled).toBe(true);
    button('Validate setup').click();
    expect(validate).toHaveBeenCalledTimes(1);
    if (!component) throw new Error('Panel was not mounted');
    await unmount(component);
    component = undefined;
    resolve(setup.validation);
    await pending;
    await tick();
    expect(validationChanged).not.toHaveBeenCalledWith('personal', true);
  });

  test.each([new HttpError(403, '', { detail: 'provider-secret' }), new NetworkError(new Error('provider-secret'))])('failures use fixed safe copy without provider errors or credential fields', async (error): Promise<void> => {
    const setup = new InMemoryPersonalOAuthSetup();
    vi.spyOn(setup, 'validate').mockRejectedValueOnce(error);
    await openPanel(setup);
    button('Validate setup').click();
    await vi.waitFor(() => expect(document.querySelector('[role="alert"]')).not.toBeNull());
    expect(document.body.textContent).not.toContain('provider-secret');
    expect(document.querySelector('input[type="password"]')).toBeNull();
    if (error instanceof HttpError) {
      expect(document.body.textContent).toContain('Administration access was lost');
      expect(document.querySelector('button')).toBeNull();
    } else {
      expect(document.body.textContent).toContain('Nothing was retried');
      expect(button('Refresh setup status').disabled).toBe(false);
    }
  });
});
