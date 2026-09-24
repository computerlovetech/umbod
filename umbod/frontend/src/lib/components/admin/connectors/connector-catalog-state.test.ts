import { describe, expect, test } from 'vitest';
import type { ConnectorListItem } from '$lib/admin/connectors';
import { ConnectorCatalogState } from './connector-catalog-state.svelte';

const connector = (id: string, isConfigured: boolean): ConnectorListItem => ({
  id,
  name: id,
  description: `${id} connector`,
  sourceLabel: 'Built-in',
  configureHref: `/admin/connectors/${id}/configuration`,
  publicationStatus: isConfigured ? 'Draft' : 'Unconfigured',
  isConfigured,
  canPublish: false,
  canUnpublish: false,
  tools: []
});

describe('ConnectorCatalogState', () => {
  test('opens without a selection and selects an available connector', () => {
    const state = new ConnectorCatalogState();
    const connectors = [connector('slack', false)];

    state.show();
    state.select('slack');

    expect(state.open).toBe(true);
    expect(state.selectedConnector(connectors)?.id).toBe('slack');
  });

  test('opens a configured connector directly', () => {
    const state = new ConnectorCatalogState();
    const connectors = [connector('slack', true)];

    state.showConfigure('slack');

    expect(state.open).toBe(true);
    expect(state.mode).toBe('configure');
    expect(state.selectedConnector(connectors)?.id).toBe('slack');
  });

  test('closing clears the selected connector', () => {
    const state = new ConnectorCatalogState();
    state.show();
    state.select('slack');

    state.close();

    expect(state.open).toBe(false);
    expect(state.selectedConnectorId).toBeNull();
  });
});
