import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import ConnectorListEmptyState from './ConnectorListEmptyState.svelte';

describe('ConnectorListEmptyState', () => {
  test.each([
    'No connectors are currently available',
    'No connectors are available yet.',
    'No OpenAPI connectors are currently available',
    'No OpenAPI connectors are available yet.',
    'No MCP connectors yet.'
  ])('renders the supplied message: %s', (message: string) => {
    const { body } = render(ConnectorListEmptyState, { props: { message } });

    expect(body).toMatch(/<p class="connector-list-empty-state[^"]*">/);
    expect(body).toContain(message);
    expect(body).not.toContain('<button');
    expect(body).not.toContain('<a ');
    expect(body).not.toContain('role="alert"');
  });

  test('renders message content as text rather than markup', () => {
    const { body } = render(ConnectorListEmptyState, {
      props: { message: '<strong>No connectors</strong>' }
    });

    expect(body).toContain('&lt;strong>No connectors&lt;/strong>');
    expect(body).not.toContain('<strong>');
  });
});
