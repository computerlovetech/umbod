import type { Transport } from '../infrastructure/transport';
import { filesystemSettingsPatchSchema, filesystemSettingsSchema, type FilesystemSettings, type FilesystemSettingsPatch } from './domain/filesystem-settings';
import type { FilesystemSettingsAdministration } from './filesystem-settings-port';

const path = '/admin/system-settings/filesystem';

export class FilesystemSettingsRoute implements FilesystemSettingsAdministration {
  constructor(private readonly transport: Transport) {}

  get(signal: AbortSignal): Promise<FilesystemSettings> {
    return this.transport.request({ method: 'GET', path, signal, outputSchema: filesystemSettingsSchema });
  }

  update(body: FilesystemSettingsPatch, signal: AbortSignal): Promise<FilesystemSettings> {
    return this.transport.request({
      method: 'PATCH', path, signal,
      requestBody: { kind: 'json', value: body, schema: filesystemSettingsPatchSchema },
      outputSchema: filesystemSettingsSchema
    });
  }
}
