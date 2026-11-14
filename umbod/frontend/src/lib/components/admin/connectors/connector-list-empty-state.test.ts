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
  ])('keeps the split workspace with an accessible empty sidebar: %s', (message: string): void => {
    const { body } = render(ConnectorListEmptyState, { props: { message } });
    const sidebar = body.match(/<aside\b[\s\S]*?<\/aside>/)?.[0];
    const detail = body.match(/<section[^>]*aria-label="Selected connector detail"[^>]*>([\s\S]*?)<\/section>/)?.[1];

    expect(body).toContain('aria-label="Connectors workspace"');
    expect(sidebar).toContain('aria-label="Connectors"');
    expect(sidebar).toMatch(/<strong[^>]*>0<\/strong>/);
    expect(sidebar).toContain(`role="img" aria-label="${message}"`);
    expect(sidebar).toContain('<svg');
    expect(sidebar).toContain('aria-hidden="true"');
    expect(detail).toBeDefined();
    expect(detail?.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
    expect(body).not.toMatch(/<p\b/);
    expect(body).not.toContain('<button');
    expect(body).not.toContain('<a ');
    expect(body).not.toContain('role="alert"');
  });

  test('uses the connector type labels supplied by its owner', (): void => {
    const { body } = render(ConnectorListEmptyState, {
      props: {
        message: 'No OpenAPI connectors',
        workspaceLabel: 'OpenAPI connectors workspace',
        sidebarLabel: 'OpenAPI connectors',
        sidebarHeading: 'OpenAPI connectors',
        detailLabel: 'Selected OpenAPI connector detail'
      }
    });

    expect(body).toContain('aria-label="OpenAPI connectors workspace"');
    expect(body).toContain('aria-label="OpenAPI connectors"');
    expect(body).toContain('<span>OpenAPI connectors</span>');
    expect(body).toContain('aria-label="Selected OpenAPI connector detail"');
  });

  test('escapes the accessible message rather than rendering markup', (): void => {
    const { body } = render(ConnectorListEmptyState, {
      props: { message: '<strong>No connectors</strong>' }
    });

    expect(body).toContain('aria-label="&lt;strong>No connectors&lt;/strong>"');
    expect(body).not.toContain('<strong>No connectors</strong>');
  });
});
