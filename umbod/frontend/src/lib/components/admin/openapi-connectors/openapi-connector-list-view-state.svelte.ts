export type OpenApiConnectorVisibleAction = 'operations';

export class OpenApiConnectorListViewState {
  visibleAction = $state<OpenApiConnectorVisibleAction | null>(null);
  openMenuConnectorId = $state<string | null>(null);
  capabilityDescriptionConnectorId = $state<string | null>(null);

  resetForSelection = (): void => {
    this.visibleAction = null;
    this.capabilityDescriptionConnectorId = null;
  };

  setMenuOpen = (connectorId: string, open: boolean): void => {
    this.openMenuConnectorId = open ? connectorId : null;
  };

  closeMenu = (): void => {
    this.openMenuConnectorId = null;
  };

  showOperations = (): void => {
    this.openMenuConnectorId = null;
    this.visibleAction = 'operations';
  };

  toggleOperations = (): boolean => {
    this.visibleAction = this.visibleAction === 'operations' ? null : 'operations';
    return this.visibleAction === 'operations';
  };

  showCapabilityDescription = (connectorId: string): void => {
    this.openMenuConnectorId = null;
    this.capabilityDescriptionConnectorId = connectorId;
  };

  closeCapabilityDescription = (): void => {
    this.capabilityDescriptionConnectorId = null;
  };
}
