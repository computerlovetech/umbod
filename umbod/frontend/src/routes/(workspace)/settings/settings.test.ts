import { expect, test, vi } from 'vitest';
import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import type { HeaderAccountIdentityState } from '#lib/header/accountIdentity.js';
import { WorkspaceAccessState } from '#lib/workspace/workspace-access-state.svelte.js';
import { WorkspaceScope } from '#lib/workspace/workspace-scope.svelte.js';
import SettingsHarness from '#lib/components/settings/SettingsHarness.test-support.svelte';
import SettingsLayout from './+layout.svelte';
import TokensPage from './tokens/+page.svelte';

const route = vi.hoisted(() => ({ id: '/(workspace)/settings' }));
vi.mock('$app/state', () => ({ page: { route } }));

const serverIdentity: HeaderAccountIdentityState = {
  kind: 'visible',
  name: 'Signed-in member',
  email: 'member@example.test',
  picture: 'https://example.test/member.webp',
  hiddenValues: { id: 'private-identity-key' }
};

function profileScope(): WorkspaceScope {
  return new WorkspaceScope(new WorkspaceAccessState(
    { profile: { get: async () => ({
      identity_key: 'private-identity-key',
      user: { id: 'member', name: 'Workspace member', email: null, picture: null },
      capabilities: { administration: false }
    }) } },
    () => serverIdentity
  ));
}

function renderProfile(workspace: WorkspaceScope): ReturnType<typeof render> {
  return render(SettingsHarness, { props: { workspace } });
}

test.each([
  { id: '/(workspace)/settings', current: '/settings', label: 'Profile' },
  { id: '/(workspace)/settings/tokens', current: '/settings/tokens', label: 'Access tokens' }
])('marks $label as the current account destination', ({ id, current, label }): void => {
  route.id = id;
  const children = createRawSnippet(() => ({ render: () => '<div>Page content</div>' }));
  const { body } = render(SettingsLayout, { props: { children, params: {}, data: { accountIdentity: { kind: 'hidden' } } } });

  expect(body).toContain('aria-label="Breadcrumb"');
  expect(body).toMatch(new RegExp(`<li aria-current="page"[^>]*>.*?${label}</li>`, 's'));
  expect(body).toMatch(/<h1[^>]*>Account settings<\/h1>/);
  expect(body).toMatch(/<nav[^>]*aria-label="Account settings"/);
  expect(body).toMatch(/>Personal<\/p>/);
  expect(body).toMatch(/>Access<\/p>/);
  expect(body.match(/<a\b[^>]*href="[^"]+"/g)).toHaveLength(2);
  expect(body).toContain('href="/settings"');
  expect(body).toContain('href="/settings/tokens"');
  expect(body).toContain(`href="${current}" aria-current="page"`);
  expect(body).toContain('<div>Page content</div>');
});

test('Profile reads the signed-in identity from workspace scope without revealing internal keys', (): void => {
  const { body } = renderProfile(profileScope());
  expect(body).toContain('>Profile</h2>');
  expect(body).toContain('>Signed-in member</dd>');
  expect(body).toContain('>member@example.test</dd>');
  expect(body).toContain('src="https://example.test/member.webp"');
  expect(body).not.toContain('private-identity-key');
  expect(body).not.toMatch(/<(?:button|input|form)\b/);
});

test('Profile uses the effective workspace identity and omits missing email', async (): Promise<void> => {
  const workspace = profileScope();
  await workspace.access.load();
  const { body } = renderProfile(workspace);
  expect(body).toContain('>Workspace member</dd>');
  expect(body).not.toContain('Email address');
  expect(body).not.toContain('member@example.test');
});

test('Profile does not render personal information when workspace scope hides identity', (): void => {
  const workspace = profileScope();
  workspace.suspendPersonal();
  const { body } = renderProfile(workspace);
  expect(body).toContain('Account details are unavailable.');
  expect(body).not.toContain('Signed-in member');
  expect(body).not.toContain('member@example.test');
  expect(body).not.toContain('member.webp');
});

test('Access tokens renders personal token management at the legacy anchor', (): void => {
  const { body, head } = render(TokensPage);
  expect(head).toContain('<title>Access tokens · Account settings · Umbod</title>');
  expect(body).toContain('id="telemetry-tokens"');
  expect(body).toMatch(/<h2[^>]*>Access tokens<\/h2>/);
  expect(body).toMatch(/<h3[^>]*>Personal access tokens<\/h3>/);
  expect(body).toContain('Loading personal access tokens');
});
