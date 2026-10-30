import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import ConnectorPageHeader from './ConnectorPageHeader.svelte';

describe('connector page header', () => {
  test.each([
    ['Connectors', 'Add connector'],
    ['OpenAPI connectors', 'Add OpenAPI connector'],
    ['MCP connectors', 'Add MCP connector']
  ])('renders %s as the only page title without an eyebrow', (title: string, addLabel: string): void => {
    const { body } = render(ConnectorPageHeader, {
      props: { title, lede: 'Review registered connectors.', addLabel, onadd: (): void => {} }
    });

    expect(body).toMatch(new RegExp(`<h1[^>]*>${title}</h1>`));
    expect(body.match(/<h1\b/g)).toHaveLength(1);
    expect(body).not.toContain('admin-eyebrow');
    expect(body).not.toContain('Umbod / Connectors');
    expect(body).toContain('Review registered connectors.');
    expect(body).toContain(`aria-label="${addLabel}"`);
  });
});
