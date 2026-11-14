import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import PersonalServerDialog from './PersonalServerDialog.svelte';
import { describe, expect, test, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { PolicyForm } from './policy-form.svelte';
import PolicyFields from './PolicyFields.svelte';
import PersonalServerPolicyPanel from './PersonalServerPolicyPanel.svelte';
import PersonalServerRegistration from './PersonalServerRegistration.svelte';
import { PersonalServerFormState } from './personal-server-form-state.svelte';
import { configurationFixture } from '$lib/admin/personal-mcp-servers/availability.test-support';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('personal server administration presentation', () => {
  test('renders a standalone selected policy panel with whole-server guidance and no second inventory', () => {
    const body = render(PersonalServerPolicyPanel).body;
    expect(body).toContain('href="/admin/group-permissions/connectors"');
    expect(body).toContain('including future tools after explicit rediscovery');
    expect(body).toContain('No per-tool approval, activation or tool grants are required');
    expect(body).toContain('Each user manages their own enablement, OAuth sign-in and private tool discovery');
    expect(body).toContain('href="/dashboard"');
    expect(body).not.toContain('<form');
    expect(body).not.toContain('<input');
    expect(body).not.toContain('<button');
    expect(body).not.toContain('<nav');
    expect(body).not.toContain('AdminShell');
    expect(body).not.toContain('ready to execute');
  });
  test('registration reuses validated metadata fields and policy controls without another inventory', () => {
    const state = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null);
    const body = render(PersonalServerRegistration, { props: { state, close: vi.fn(), reload: vi.fn() } }).body;
    expect(body).toContain('Register MCP server with personal authorization');
    expect(body).toContain('Your organisation manages the connector; each user authorizes access using their own account.');
    expect(body).toContain('Server details and the endpoint cannot be changed after registration; OAuth settings can be updated separately.');
    expect(body).not.toContain('Register personal MCP server');
    expect(body).toContain('Registration starts unpublished');
    expect(body).toContain('No discovery, group grants, user enablement or consent');
    expect(body).toContain('Registration path identifier');
    expect(body).toContain('does not provide a shared proxy connection');
    expect(body).toContain('Register unpublished server');
    expect(body).not.toContain('<nav');
    expect(body).not.toContain('bearerToken');
  });
  test('registration explains server fields with accessible helpers, useful placeholders and a suffix-only path', () => {
    const state = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null);
    const document = new Window().document;
    document.body.innerHTML = render(PersonalServerRegistration, { props: { state, close: vi.fn(), reload: vi.fn() } }).body;
    const endpoint = document.getElementById('personal-endpoint')!;
    expect(endpoint.getAttribute('type')).toBe('url');
    expect(endpoint.getAttribute('placeholder')).toBe('https://mcp.example.com/mcp');
    for (const id of ['personal-name', 'personal-endpoint', 'personal-prefix', 'personal-description', 'personal-path']) {
      const field = document.getElementById(id)!;
      expect(field.getAttribute('aria-describedby')).toBe(`${id}-helper`);
      expect(document.getElementById(`${id}-helper`)?.textContent?.length).toBeGreaterThan(30);
    }
    const path = document.getElementById('personal-path')!;
    expect(path.getAttribute('value')).toBe('');
    expect(path.getAttribute('maxlength')).toBe('63');
    expect(path.getAttribute('pattern')).toBe('[a-z0-9][a-z0-9\\-]{0,62}');
    expect(path.parentElement?.querySelector('[aria-hidden="true"]')?.textContent).toBe('/mcp/proxies/');
    expect(document.getElementById('personal-path-helper')?.textContent).toContain('Enter only the unique identifier after /mcp/proxies/');
    expect(document.getElementById('personal-path-helper')?.textContent).toContain('does not provide a shared proxy connection or authorize execution');
    expect(document.body.textContent).toContain('cannot be changed after registration');
    expect(document.getElementById('personal-description')?.getAttribute('maxlength')).toBe('300');
    expect(document.body.textContent).not.toContain('Dedicated endpoint');
  });
  test('read-only policy guidance and registration retain unique IDs and scoped accessible fields', () => {
    const document = new Window().document;
    const registration = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null);
    registration.form.setKind('preconfigured_confidential');
    document.body.innerHTML = `<section data-scope="selected">${render(PersonalServerPolicyPanel).body}</section><section data-scope="registration">${render(PersonalServerRegistration, { props: { state: registration, close: vi.fn(), reload: vi.fn() } }).body}</section>`;
    const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
    expect(new Set(ids).size).toBe(ids.length);
    const scope = document.querySelector('[data-scope="registration"]')!;
    for (const label of scope.querySelectorAll('label[for]')) {
      const target = document.getElementById(label.getAttribute('for')!);
      expect(target).not.toBeNull();
      expect(scope.contains(target!)).toBe(true);
      expect(target?.matches('input, button[role="combobox"]')).toBe(true);
    }
    for (const control of scope.querySelectorAll('[aria-describedby]')) {
      for (const id of control.getAttribute('aria-describedby')!.split(' ')) {
        const helper = document.getElementById(id);
        expect(helper).not.toBeNull();
        expect(scope.contains(helper!)).toBe(true);
      }
    }
    const labels = [...scope.querySelectorAll('label')].map((label) => label.textContent);
    for (const name of ['OAuth application setup', 'Requested scopes', 'Exact HTTPS issuer URL', 'Client ID', 'Token endpoint authentication', 'Fresh client secret']) expect(labels).toContain(name);
  });
  test('dynamic clients expose no stored or shared credential controls', () => {
    const body = render(PolicyFields, { props: { form: new PolicyForm(), idPrefix: 'personal' } }).body;
    expect(body).toContain('OAuth application setup');
    expect(body).toContain('Automatic registration');
    expect(body).toContain('role="combobox"');
    expect(body).not.toContain('<select');
    expect(body).not.toContain('Dynamic public');
    expect(body).not.toContain('Preconfigured public');
    expect(body).not.toContain('Preconfigured confidential');
    expect(body).toContain("These settings identify Umbod's application, not a user's login method.");
    expect(body).toContain('Users still connect their own accounts.');
    expect(body).toContain("The provider registers Umbod's application automatically.");
    expect(body).toContain('value="dynamic_public"');
    expect(body).toContain('Requested scopes');
    expect(body).toContain('ordinary spaces');
    expect(body).toContain('provider defaults');
    expect(body).not.toContain('id="personal-client-secret"');
    expect(body).not.toContain('id="personal-issuer"');
    expect(body).not.toContain('bearerToken');
  });
  test('public clients display exact issuer and ID but no secret field', () => {
    const form = new PolicyForm();
    form.reset({ ...policyFixture(), client: { kind: 'preconfigured_public', issuer_url: 'https://Issuer.test:443/Exact/', client_id: 'public-app' } });
    const body = render(PolicyFields, { props: { form, idPrefix: 'personal' } }).body;
    expect(body).toContain('value="https://Issuer.test:443/Exact/"');
    expect(body).toContain('value="public-app"');
    expect(body).toContain('An administrator provides the client ID of an existing application registered with the provider.');
    expect(body).not.toContain("The provider registers Umbod's application automatically.");
    expect(body).not.toContain('id="personal-client-secret"');
  });
  test('confidential reads present configured status with an empty required password and both explicit methods', () => {
    const form = new PolicyForm();
    form.reset({ ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_post', client_secret_configured: true } });
    const body = render(PolicyFields, { props: { form, idPrefix: 'personal' } }).body;
    expect(body).toContain('Client secret configured');
    expect(body).toContain('placeholder="https://auth.example.com"');
    expect(body).toContain('which may differ from the MCP endpoint');
    expect(body).toContain("This is not a user's account ID or access token.");
    expect(body).toContain('Basic sends application credentials in an HTTP header');
    expect(body).toContain("An administrator provides an existing application's client ID and secret. The secret is not a user's password.");
    expect(body).toMatch(/id="personal-client-secret"[^>]*type="password"[^>]*autocomplete="new-password"[^>]*required[^>]*value=""/);
    const document = new Window().document;
    document.body.innerHTML = body;
    const authentication = document.getElementById('personal-auth-method');
    expect(authentication?.getAttribute('role')).toBe('combobox');
    expect(authentication?.getAttribute('value')).toBe('client_secret_post');
    expect(authentication?.textContent).toContain('POST (client_secret_post)');
    expect(document.querySelectorAll('select')).toHaveLength(0);
    expect(body).toContain('Required for every confidential write');
    expect(body).not.toContain('Leave blank to keep');
    expect(body).not.toContain('********');
  });
  test('registration retains native validation and the dialog exposes accessible dismissal', () => {
    const registration = readFileSync('src/lib/components/admin/personal-mcp-servers/PersonalServerRegistration.svelte', 'utf8');
    expect(registration).toContain('captureInvalidSubmission(state.handleNativeInvalid)');
    expect(registration).not.toContain('novalidate');
    const body = render(PersonalServerDialog, { props: {
      title: 'Confirm change', titleId: 'dialog-title', descriptionId: 'dialog-description', close: vi.fn(),
      children: createRawSnippet(() => ({ render: (): string => '<p id="dialog-description">Review this change.</p>' }))
    } }).body;
    expect(body).toContain('<dialog role="dialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-description"');
    expect(body).toContain('id="dialog-title" tabindex="-1"');
    expect(body).toContain('aria-label="Close"');
    expect(body).not.toContain('autofocus');
    expect(body).not.toContain(' open');
  });
  test('registration uncertainty keeps its dialog mounted and exposes full workspace reload after close', () => {
    const page = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
    expect(page).toContain('state.operations.loseAccess, state.operations.setRegistrationLocked');
    expect(page).toContain("state.modal === 'personal' && !state.operations.authenticationLost");
    expect(page).not.toContain("state.modal === 'personal' && !state.operations.locked");
    expect(page).toContain("{#if registration.blocked && state.modal !== 'personal'}");
    expect(page).toContain('All workspace changes remain blocked until a full server reload');
    expect(page).toContain('{#if !state.operations.registrationLocked}');
    expect(page).toContain('if (registration.blocked) window.location.reload()');
    expect(page).toContain('disabled={state.operations.locked}');
    expect(page).toContain('<Button aria-label="Add MCP connector" disabled={state.operations.locked}');
  });
  test('the old route has no UI and the surviving workspace owns both mode choices', () => {
    const workspace = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
    const shell = readFileSync('src/lib/components/admin/AdminShell.svelte', 'utf8');
    expect(workspace).toContain('onclick={(event) => state.beginCreate(registration.availability, event.currentTarget)}');
    expect(workspace).toContain('Both options are organisation-managed.');
    expect(workspace).toContain('Choose shared authorization or personal authorization, where each user authorizes access using their own account.');
    expect(workspace).not.toContain('User-managed');
    expect(workspace).toContain('>Shared</Button>');
    expect(workspace).not.toContain('An operator must');
    expect(workspace).not.toContain('View startup settings');
    expect(workspace).not.toContain('Reload availability');
    expect(workspace).not.toContain('User OAuth availability');
    expect(workspace).toContain('>Personal</Button>');
    expect(workspace).toMatch(/<div class="connector-mode-options">\s*<Button[^\n]+>Shared<\/Button>\s*<Button[^\n]+>Personal<\/Button>\s*<\/div>/);
    expect(workspace).toContain('.connector-mode-options { display: grid; flex-shrink: 0; gap: .75rem; }');
    expect(workspace).toContain('disabled={!registration.canRegister}');
    expect(workspace).toContain('<PersonalServerRegistration');
    expect(workspace).not.toContain('/admin/personal-mcp-servers');
    expect(shell).not.toContain('personalMcpServers');
  });
});
