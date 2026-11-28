import { z } from 'zod';

export const portableConnectorSettingsSchema = z.strictObject({ enabled: z.boolean() });
export const portableConnectorSettingsPatchSchema = z.strictObject({ enabled: z.boolean() });

export type PortableConnectorSettings = z.infer<typeof portableConnectorSettingsSchema>;
export type PortableConnectorSettingsPatch = z.infer<typeof portableConnectorSettingsPatchSchema>;
