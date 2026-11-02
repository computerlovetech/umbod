import { z } from 'zod';

export const workspaceProfileSchema = z.object({
  user: z.object({
    id: z.string(),
    name: z.string(),
    email: z.string().nullable(),
    picture: z.string().nullable()
  }),
  capabilities: z.object({ administration: z.boolean() })
});

export type WorkspaceProfile = z.infer<typeof workspaceProfileSchema>;
