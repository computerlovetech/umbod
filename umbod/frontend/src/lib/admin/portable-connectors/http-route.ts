import type { Transport } from '../infrastructure/transport.js';
import {
  portableConnectorConfigurationSchema,
  portableConnectorListSchema,
  replacePortableConfigurationSchema,
  type PortableConnectorConfiguration,
  type PortableConnectorList,
  type ReplacePortableConfiguration
} from './domain/schemas.js';
import type { PortableConnectors } from './port.js';

const path = '/admin/portable-connectors';

function configurationPath(id: string): string {
  return `${path}/${encodeURIComponent(id)}/configuration`;
}

export class PortableConnectorsRoute implements PortableConnectors {
  constructor(private readonly transport: Transport) {}

  list(): Promise<PortableConnectorList> {
    return this.transport.request({ method: 'GET', path, outputSchema: portableConnectorListSchema });
  }

  getConfiguration(id: string, signal: AbortSignal): Promise<PortableConnectorConfiguration> {
    return this.transport.request({ method: 'GET', path: configurationPath(id), signal, outputSchema: portableConnectorConfigurationSchema });
  }

  replaceConfiguration(id: string, value: ReplacePortableConfiguration, signal: AbortSignal): Promise<PortableConnectorConfiguration> {
    return this.transport.request({
      method: 'PUT',
      path: configurationPath(id),
      signal,
      requestBody: { kind: 'json', value, schema: replacePortableConfigurationSchema },
      outputSchema: portableConnectorConfigurationSchema
    });
  }
}
