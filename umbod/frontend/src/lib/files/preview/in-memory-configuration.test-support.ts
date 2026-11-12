import { previewConfigurationSchema, type PreviewConfiguration, type PreviewConfigurationProvider } from './configuration';

export class InMemoryPreviewConfiguration implements PreviewConfigurationProvider {
  constructor(private readonly filesystemPreviewMaxBytes: number) {}

  async get(): Promise<PreviewConfiguration> {
    return previewConfigurationSchema.parse({ filesystemPreviewMaxBytes: this.filesystemPreviewMaxBytes });
  }
}
