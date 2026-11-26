import { expect, test } from 'vitest';
import { catalogueConnectorSchema } from './domain/schemas';
import { catalogueSidebarItem } from './presentation';

const connector = {
  connector_id: 'computerlove',
  kind: 'downstream_mcp',
  display_name: 'Computerlove',
  capability_description: 'Manage downstream tools',
  ownership: 'shared',
  capabilities: []
};

test('a stored connector icon reaches the user sidebar item', (): void => {
  const iconUrl = 'https://icons.example.test/logo.png';
  const parsed = catalogueConnectorSchema.parse({ ...connector, icon_url: iconUrl });
  expect(catalogueSidebarItem(parsed).iconDataUrl).toBe(iconUrl);
});

test('an iconless connector leaves the sidebar initials fallback available', (): void => {
  const parsed = catalogueConnectorSchema.parse(connector);
  expect(catalogueSidebarItem(parsed)).not.toHaveProperty('iconDataUrl');
});
