import type { CatalogueConnector, UserCatalogue } from './domain/schemas';

export const sharedConnector: CatalogueConnector = {
  connector_id: 'shared',
  kind: 'downstream_mcp',
  display_name: 'Shared calendar',
  capability_description: 'Calendar tools',
  ownership: 'shared',
  capabilities: [{ kind: 'tool', key: 'events', name: 'Events', description: 'Read calendar events' }]
};

export const personalConnector: CatalogueConnector = {
  connector_id: 'calendar',
  kind: 'downstream_mcp',
  display_name: 'My calendar',
  capability_description: 'Personal calendar tools',
  ownership: 'personal',
  capabilities: []
};

export const catalogue: UserCatalogue = {
  identity_key: 'account-one',
  personal_enabled: true,
  connectors: [sharedConnector, personalConnector]
};
