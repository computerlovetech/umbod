import type { PortableConnectors } from '#lib/admin/portable-connectors/port.js';
import type { PortableConnectorRow, UnifiedConnectorInventory } from '#lib/admin/unified-connectors.js';
import { PortableConfigurationState } from './portable-configuration-state.svelte.js';

export type PortableConnectorWorkspaceData = UnifiedConnectorInventory & {
  connectors: readonly PortableConnectorRow[];
  selected: PortableConnectorRow | undefined;
};

export class PortableConnectorWorkspaceState {
  readonly configuration: PortableConfigurationState | undefined;
  get items(): readonly PortableConnectorRow[] {
    const selected = this.configuration?.connector;
    return this.data.connectors.map((connector) => selected?.id === connector.id ? selected : connector);
  }

  constructor(readonly data: PortableConnectorWorkspaceData, api: PortableConnectors) {
    this.configuration = data.selected && new PortableConfigurationState(data.selected, api);
  }
}
