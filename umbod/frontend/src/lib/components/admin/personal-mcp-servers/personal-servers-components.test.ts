import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import PersonalServerDialog from './PersonalServerDialog.svelte';
import { describe, expect, test, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { InMemoryPersonalServers } from '#lib/admin/personal-mcp-servers/in-memory.js';
import { policyFixture } from '#lib/admin/personal-mcp-servers/fixtures.test-support.js';
import { PolicyForm } from './policy-form.svelte';
import PolicyFields from './PolicyFields.svelte';
import PersonalServerPolicyPanel from './PersonalServerPolicyPanel.svelte';
import PersonalServerRegistration from './PersonalServerRegistration.svelte';
import { PersonalServerFormState } from './personal-server-form-state.svelte';
import { configurationFixture } from '#lib/admin/personal-mcp-servers/availability.test-support.js';

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
    const state = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null, null);
    const body = render(PersonalServerRegistration, { props: { state, close: vi.fn(), reload: vi.fn() } }).body;
    expect(body).toContain('Register MCP server with personal authorization');


    expect(body).not.toContain('Register personal MCP server');


    expect(body).toContain('Registration path identifier');

    expect(body).toContain('Register unpublished server');
    expect(body).not.toContain('<nav');
    expect(body).not.toContain('bearerToken');
  });
  test('registration explains server fields with accessible helpers, useful placeholders and a suffix-only path', () => {
    const state = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null, null);
    const document = new Window().document;
    document.body.innerHTML = render(PersonalServerRegistration, { props: { state, close: vi.fn(), reload: vi.fn() } }).body;
    const endpoint = document.getElementById('personal-endpoint')!;
    expect(endpoint.getAttribute('type')).toBe('url');
    expect(endpoint.getAttribute('placeholder')).toBe('https://mcp.example.com/mcp');
    for (const id of ['personal-name', 'personal-endpoint', 'personal-prefix', 'personal-description', 'personal-path']) {
      const field = document.getElementById(id)!;
      expect(field.getAttribute('placeholder')).toBeTruthy();
      expect(document.querySelector(`label[for="${id}"]`)).not.toBeNull();


    }
    const path = document.getElementById('personal-path')!;
    expect(path.getAttribute('value')).toBe('');
    expect(path.getAttribute('maxlength')).toBe('63');
    expect(path.getAttribute('pattern')).toBe('[a-z0-9][a-z0-9\\-]{0,62}');
    expect(path.parentElement?.querySelector('[aria-hidden="true"]')?.textContent).toBe('/mcp/proxies/');



    expect(document.getElementById('personal-description')?.getAttribute('maxlength')).toBe('300');
    expect(document.body.textContent).not.toContain('Dedicated endpoint');
  });
  test('read-only policy guidance and registration retain unique IDs and scoped accessible fields', () => {
    const document = new Window().document;
    const registration = new PersonalServerFormState(new InMemoryPersonalServers(), { get: async () => configurationFixture() }, null, null);
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
    for (const name of ['OAuth application setup', 'Exact HTTPS issuer URL', 'Client ID', 'Token endpoint authentication', 'Fresh client secret']) expect(labels).toContain(name);
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



    expect(body).toContain('value="automatic"');
    expect(body).toContain('Requested scopes');


    expect(body).not.toContain('provider defaults');
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


    expect(body).not.toContain('id="personal-client-secret"');
  });
  test('confidential reads present configured status with an empty required password and both explicit methods', () => {
    const form = new PolicyForm();
    form.reset({ ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_post', client_secret_configured: true } });
    const body = render(PolicyFields, { props: { form, idPrefix: 'personal' } }).body;
    expect(body).toContain('Client secret configured');
    expect(body).toContain('placeholder="https://auth.example.com"');




    expect(body).toMatch(/id="personal-client-secret"[^>]*type="password"[^>]*autocomplete="new-password"[^>]*required[^>]*value=""/);
    const document = new Window().document;
    document.body.innerHTML = body;
    const authentication = document.getElementById('personal-auth-method');
    expect(authentication?.getAttribute('role')).toBe('combobox');
    expect(authentication?.getAttribute('value')).toBe('client_secret_post');
    expect(authentication?.textContent).toContain('POST (client_secret_post)');
    expect(document.querySelectorAll('select')).toHaveLength(0);

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
    expect(page).toContain('workspace.operations.loseAccess, workspace.operations.setRegistrationLocked');
    expect(page).toContain("workspace.modal === 'personal' && !workspace.operations.authenticationLost");
    expect(page).not.toContain("workspace.modal === 'personal' && !workspace.operations.locked");
    expect(page).toContain("{#if registration.blocked && workspace.modal !== 'personal'}");
    expect(page).toContain('All workspace changes remain blocked until a full server reload');
    expect(page).toContain('{#if !workspace.operations.registrationLocked}');
    expect(page).toContain('if (registration.blocked) window.location.reload()');
    expect(page).toContain('disabled: () => workspace.operations.locked');
  });
  test('the consolidated workspace and navigation do not link to the retired personal-server route', () => {
    const workspace = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
    const shell = readFileSync('src/lib/components/admin/AdminShell.svelte', 'utf8');
    expect(workspace).not.toContain('/admin/personal-mcp-servers');
    expect(shell).not.toContain('personalMcpServers');
  });
});
