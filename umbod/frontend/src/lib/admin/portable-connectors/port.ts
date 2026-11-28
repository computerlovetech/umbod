import type { PortableConnectorConfiguration, PortableConnectorList, ReplacePortableConfiguration } from './domain/schemas.js';

export interface PortableConnectors {
  list(): Promise<PortableConnectorList>;
  getConfiguration(id: string, signal: AbortSignal): Promise<PortableConnectorConfiguration>;
  replaceConfiguration(id: string, body: ReplacePortableConfiguration, signal: AbortSignal): Promise<PortableConnectorConfiguration>;
}
