import { render } from 'svelte/server';
import { describe, expect, test } from 'vitest';
import ConnectorTabs from './ConnectorTabs.svelte';

describe('ConnectorTabs', () => {
  test('switches between connector types and identifies the active page', () => {
    const { body } = render(ConnectorTabs, { props: { activeTab: 'openapi' } });

    expect(body).toContain('aria-label="Connector type"');
    expect(body).toMatch(/<a[^>]*href="\/admin\/connectors\?capability=tools"[^>]*>\s*Connector catalog/);
    expect(body).toMatch(/<a[^>]*href="\/admin\/openapi-connectors\?capability=tools"[^>]*aria-current="page"[^>]*>\s*OpenAPI connectors/);
  });
});
