import type { Transport } from '../infrastructure/transport';
import {
  portableConnectorSettingsPatchSchema,
  portableConnectorSettingsSchema,
  type PortableConnectorSettings,
  type PortableConnectorSettingsPatch
} from './domain/portable-connector-settings';
import type { PortableConnectorSettingsAdministration } from './portable-connector-settings-port';

const path = '/admin/system-settings/portable-connectors';

export class PortableConnectorSettingsRoute implements PortableConnectorSettingsAdministration {
  constructor(private readonly transport: Transport) {}

  get(signal: AbortSignal): Promise<PortableConnectorSettings> {
    return this.transport.request({ method: 'GET', path, signal, outputSchema: portableConnectorSettingsSchema });
  }

  update(body: PortableConnectorSettingsPatch, signal: AbortSignal): Promise<PortableConnectorSettings> {
    return this.transport.request({
      method: 'PATCH', path, signal,
      requestBody: { kind: 'json', value: body, schema: portableConnectorSettingsPatchSchema },
      outputSchema: portableConnectorSettingsSchema
    });
  }
}
