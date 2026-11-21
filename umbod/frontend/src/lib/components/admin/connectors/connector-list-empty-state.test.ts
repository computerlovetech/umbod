import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import ConnectorListEmptyState from './ConnectorListEmptyState.svelte';

describe('ConnectorListEmptyState', () => {
  test('keeps the split workspace with an accessible empty sidebar and blank detail pane', (): void => {
    const { body } = render(ConnectorListEmptyState, { props: { detailLabel: 'Selected connector detail' } });
    const sidebar = body.match(/<aside\b[\s\S]*?<\/aside>/)?.[0];
    const detail = body.match(/<section[^>]*aria-label="Selected connector detail"[^>]*>([\s\S]*?)<\/section>/)?.[1];

    expect(body).toContain('aria-label="Connectors workspace"');
    expect(sidebar).toContain('aria-label="Connectors"');
    expect(sidebar).toMatch(/<strong[^>]*>0<\/strong>/);
    expect(sidebar).toContain('role="img" aria-label="No connectors yet."');
    expect(sidebar).toContain('<svg');
    expect(sidebar).toContain('aria-hidden="true"');
    expect(detail).toBeDefined();
    expect(detail?.replace(/<!--[\s\S]*?-->/g, '').trim()).toBe('');
    expect(body).not.toMatch(/<p\b/);
    expect(body).not.toContain('<button');
    expect(body).not.toContain('<a ');
    expect(body).not.toContain('role="alert"');
  });
});
