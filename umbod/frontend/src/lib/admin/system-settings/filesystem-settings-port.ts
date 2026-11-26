import type { FilesystemSettings, FilesystemSettingsPatch } from './domain/filesystem-settings';

export interface FilesystemSettingsAdministration {
  get(signal: AbortSignal): Promise<FilesystemSettings>;
  update(body: FilesystemSettingsPatch, signal: AbortSignal): Promise<FilesystemSettings>;
}
