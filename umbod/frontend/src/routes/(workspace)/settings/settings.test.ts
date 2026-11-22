import { expect, test } from 'vitest';
import { render } from 'svelte/server';
import SettingsPage from './+page.svelte';
import TokensPage from './tokens/+page.svelte';

test('Settings links to Tokens without rendering token management', (): void => {
  const { body, head } = render(SettingsPage);

  expect(head).toContain('<title>Settings · Umbod</title>');
  expect(body).toMatch(/<h1[^>]*>Settings<\/h1>/);
  expect(body).toMatch(/<a[^>]*href="\/settings\/tokens"[^>]*>Tokens<\/a>/);
  expect(body).not.toContain('Personal access tokens');
});

test('Tokens renders personal token management and a way back to Settings', (): void => {
  const { body, head } = render(TokensPage);

  expect(head).toContain('<title>Tokens · Settings · Umbod</title>');
  expect(body).toMatch(/<h1[^>]*>Tokens<\/h1>/);
  expect(body).toMatch(/<h2[^>]*>Personal access tokens<\/h2>/);
  expect(body).toMatch(/<a[^>]*href="\/settings"[^>]*>Back to Settings<\/a>/);
});
