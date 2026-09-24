import type { ConnectorListItem } from '$lib/admin/connectors';

export class ConnectorCatalogState {
  open = $state(false);
  mode = $state<'add' | 'configure'>('add');
  selectedConnectorId = $state<string | null>(null);

  show = (): void => {
    this.open = true;
    this.mode = 'add';
    this.selectedConnectorId = null;
  };

  showConfigure = (connectorId: string): void => {
    this.open = true;
    this.mode = 'configure';
    this.selectedConnectorId = connectorId;
  };

  close = (): void => {
    this.open = false;
    this.selectedConnectorId = null;
  };

  select = (connectorId: string): void => {
    this.selectedConnectorId = connectorId;
  };

  clearSelection = (): void => {
    this.selectedConnectorId = null;
  };

  selectedConnector = (connectors: ConnectorListItem[]): ConnectorListItem | null => {
    return connectors.find((connector) => connector.id === this.selectedConnectorId) ?? null;
  };

  handleKeydown = (event: KeyboardEvent): void => {
    if (event.key === 'Escape' && this.open) {
      this.close();
    }
  };
}
