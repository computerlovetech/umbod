import { render } from 'svelte/server';
import { createRawSnippet } from 'svelte';
import PersonalServerDialog from './PersonalServerDialog.svelte';
import { describe, expect, test, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { InMemoryPersonalServers } from '$lib/admin/personal-mcp-servers/in-memory';
import { policyFixture } from '$lib/admin/personal-mcp-servers/fixtures.test-support';
import { PolicyForm } from './policy-form.svelte';
import PolicyFields from './PolicyFields.svelte';
import PersonalServersPage from './PersonalServersPage.svelte';

vi.mock('$app/state', () => ({ navigating: { to: null, from: null } }));

describe('personal server administration presentation', () => {
  test('renders dedicated Admin navigation, permissions link and truthful persistent guidance', () => {
    const body = render(PersonalServersPage, { props: { accountIdentity: { kind: 'hidden' }, api: new InMemoryPersonalServers() } }).body;
    expect(body).toMatch(/href="\/admin\/personal-mcp-servers"[^>]*aria-current="page"/);
    expect(body).toContain('Personal MCP servers');
    expect(body).toContain('href="/admin/group-permissions"');
    expect(body).toContain('href="/admin/downstream-mcp-connectors"');
    expect(body).toContain('Publication allows selection by explicitly permitted groups');
    expect(body).toContain('Approved tool contracts (API-only in this interface), activation and tool permissions');
    expect(body).toContain('not universal access');
    expect(body).not.toContain('ready to use');
    expect(body).not.toContain('ready to execute');
    expect(body).toContain('Reload servers');
  });
  test('dynamic clients expose no stored or shared credential controls', () => {
    const body = render(PolicyFields, { props: { form: new PolicyForm() } }).body;
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
    const body = render(PolicyFields, { props: { form } }).body;
    expect(body).toContain('value="https://Issuer.test:443/Exact/"');
    expect(body).toContain('value="public-app"');
    expect(body).not.toContain('id="personal-client-secret"');
  });
  test('confidential reads present configured status with an empty required password and both explicit methods', () => {
    const form = new PolicyForm();
    form.reset({ ...policyFixture(), client: { kind: 'preconfigured_confidential', issuer_url: 'https://issuer.test', client_id: 'app', token_endpoint_auth_method: 'client_secret_post', client_secret_configured: true } });
    const body = render(PolicyFields, { props: { form } }).body;
    expect(body).toContain('Client secret configured');
    expect(body).toMatch(/id="personal-client-secret"[^>]*type="password"[^>]*autocomplete="new-password"[^>]*required[^>]*value=""/);
    expect(body).toContain('client_secret_basic');
    expect(body).toContain('client_secret_post');
    expect(body).toContain('Required for every confidential write');
    expect(body).not.toContain('Leave blank to keep');
    expect(body).not.toContain('********');
  });
  test('registration, policy and publication confirmation copy keeps separate prerequisites explicit', () => {
    const page = readFileSync('src/lib/components/admin/personal-mcp-servers/PersonalServersPage.svelte', 'utf8');
    expect(page).toContain('Registration starts unpublished. No discovery, group grants, user enablement or consent is performed.');
    expect(page).toContain("ALL users' saved authorizations and pending sign-ins");
    expect(page).toContain('User enablement, publication and group grants persist');
    expect(page).toContain('Remote tokens are not revoked');
    expect(page).toContain('After the user catalogue reloads');
    expect(page).toContain('Remove connector and tool grants first');
    expect(page).toContain('unique, fixed registration path identifier');
    expect(page).toContain('does not provide a shared proxy connection or authorize execution');
    expect(page).toContain('Server details and endpoint cannot be changed after registration');
    expect(page).toContain('<dt>Server ID</dt><dd>{state.selected.connector_id}</dd>');
    expect(page).toContain('Review changes');
    expect(page).not.toContain('discover(');
    expect(page).not.toContain('configuredSecret=');
    expect(page).not.toContain('localStorage');
    expect(page).not.toContain('$effect');
    expect(page).toContain('return state.dispose');
    expect(page).toContain('<fieldset disabled={state.locked');
  });
  test('uses labelled native dialogs and invalid capture on both forms without disabling native validation', () => {
    const page = readFileSync('src/lib/components/admin/personal-mcp-servers/PersonalServersPage.svelte', 'utf8');
    expect(page.match(/captureInvalidSubmission\(state.handleNativeInvalid\)/g)).toHaveLength(2);
    expect(page.match(/<PersonalServerDialog /g)).toHaveLength(2);
    expect(page).not.toContain('AdminModalShell');
    expect(page).not.toContain('novalidate');
    expect(page).not.toContain('class:');
    expect(page).toContain('role="alert"');
    expect(page).toContain('id="personal-servers-heading" tabindex="-1"');
    const body = render(PersonalServerDialog, { props: {
      title: 'Confirm change', titleId: 'dialog-title', descriptionId: 'dialog-description', close: vi.fn(),
      children: createRawSnippet(() => ({ render: (): string => '<p id="dialog-description">Review this change.</p>' }))
    } }).body;
    expect(body).toContain('<dialog aria-labelledby="dialog-title" aria-describedby="dialog-description"');
    expect(body).toContain('id="dialog-title" tabindex="-1"');
    expect(body).toContain('aria-label="Close"');
    expect(body).not.toContain('autofocus');
    expect(body).not.toContain(' open');
  });
  test('shared workspace links to the personal allowlist and thin personal route wires selected URL', () => {
    const sharedPage = readFileSync('src/lib/components/admin/downstream-mcp-connectors/DownstreamMcpPageContent.svelte', 'utf8');
    const route = readFileSync('src/routes/admin/personal-mcp-servers/+page.svelte', 'utf8');
    expect(sharedPage).toContain('href="/admin/personal-mcp-servers"');
    expect(route).toContain('<PersonalServersPage');
    expect(route).toContain('{#key data}');
    expect(route).toContain("url.searchParams.set('connector', id)");
    expect(route).toContain('replaceState(url, {})');
    expect(route).not.toContain('fetch(');
  });
});
