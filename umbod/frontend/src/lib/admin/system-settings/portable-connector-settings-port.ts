import type { PortableConnectorSettings, PortableConnectorSettingsPatch } from './domain/portable-connector-settings';

export interface PortableConnectorSettingsAdministration {
  get(signal: AbortSignal): Promise<PortableConnectorSettings>;
  update(body: PortableConnectorSettingsPatch, signal: AbortSignal): Promise<PortableConnectorSettings>;
}
