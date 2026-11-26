import { z } from 'zod';

export const filesystemSettingsSchema = z.strictObject({
  require_mcp_file_deletion_approval: z.strictObject({
    value: z.boolean(),
    source: z.enum(['admin_override', 'deployment_default', 'built_in_default'])
  })
});

export const filesystemSettingsPatchSchema = z.strictObject({
  require_mcp_file_deletion_approval: z.discriminatedUnion('operation', [
    z.strictObject({ operation: z.literal('set'), value: z.boolean() }),
    z.strictObject({ operation: z.literal('reset') })
  ])
});

export type FilesystemSettings = z.infer<typeof filesystemSettingsSchema>;
export type FilesystemSettingsPatch = z.infer<typeof filesystemSettingsPatchSchema>;
