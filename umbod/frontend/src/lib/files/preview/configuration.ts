import { z } from 'zod';

export const previewConfigurationSchema = z.object({
  filesystemPreviewMaxBytes: z.number().int().positive().max(Number.MAX_SAFE_INTEGER)
});

export type PreviewConfiguration = z.infer<typeof previewConfigurationSchema>;

export interface PreviewConfigurationProvider {
  get(): Promise<PreviewConfiguration>;
}
