import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import SubpageContainer from './SubpageContainer.svelte';
import SubpageNavigation from './SubpageNavigation.svelte';

const navigation = createRawSnippet(() => ({ render: (): string => '<nav aria-label="Sections"><a href="/first">First</a></nav>' }));
const children = createRawSnippet(() => ({ render: (): string => '<section aria-label="Selected content">Current page</section>' }));

describe('shared subpage presentation', (): void => {
  test.each(['Connectors', 'OpenAPI connectors', 'MCP connectors', 'Getting started'])('renders one %s heading with navigation and selected content', (title: string): void => {
    const body = render(SubpageContainer, { props: { title, lede: 'Choose a section.', headingId: 'page-title', navigation, children } }).body;
    expect(body.match(/<h1\b/g)).toHaveLength(1);
    expect(body).toContain(`id="page-title" tabindex="-1">${title}</h1>`);
    expect(body).toContain('Choose a section.');
    expect(body).toContain('aria-label="Sections"');
    expect(body).toContain('aria-label="Selected content"');
    expect(body).not.toContain('<button');
  });

  test('renders feature-owned actions without requiring an add workflow', (): void => {
    const actions = createRawSnippet(() => ({ render: (): string => '<button type="button">Create token</button>' }));
    const body = render(SubpageContainer, { props: { title: 'Tokens', lede: 'Manage tokens.', actions, navigation, children } }).body;
    expect(body).toContain('<button type="button">Create token</button>');
    expect(body).not.toContain('Add connector');
  });

  test('uses real subpage links and identifies exactly one current page', (): void => {
    const body = render(SubpageNavigation, { props: {
      label: 'Setup sections', activeId: 'telemetry', links: [
        { id: 'connect', label: 'Connect your harness', href: '/getting-started' },
        { id: 'telemetry', label: 'Set up telemetry', href: '/getting-started/telemetry' }
      ]
    } }).body;
    expect(body).toContain('aria-label="Setup sections"');
    expect(body.match(/aria-current="page"/g)).toHaveLength(1);
    expect(body).toMatch(/href="\/getting-started\/telemetry" aria-current="page"[^>]*>Set up telemetry/);
    expect(body).not.toContain('role="tab"');
  });
});
