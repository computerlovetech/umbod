import { z } from 'zod';

const nonblankText = z.string().refine((value: string): boolean => value.trim().length > 0);
const expiration = z.iso.datetime({ offset: true }).nullable();
export const agentIdSchema = z.string().length(32).regex(/^[0-9a-f]+$/);

export const agentTokenMetadataSchema = z.strictObject({
  agent_id: agentIdSchema,
  display_name: nonblankText,
  group_id: nonblankText,
  credential_id: agentIdSchema,
  expires_at: expiration,
  status: z.enum(['active', 'expired', 'revoked'])
});

export const agentTokenListSchema = z.array(agentTokenMetadataSchema);
export const createAgentTokenSchema = z.strictObject({
  display_name: nonblankText,
  group_id: nonblankText,
  expires_at: expiration
});
export const rotateAgentTokenSchema = z.strictObject({ expires_at: expiration });
export const issuedAgentTokenSchema = z.strictObject({
  metadata: agentTokenMetadataSchema,
  token: z.string().min(1)
});

export type AgentTokenMetadata = z.infer<typeof agentTokenMetadataSchema>;
export type CreateAgentTokenInput = z.infer<typeof createAgentTokenSchema>;
export type RotateAgentTokenInput = z.infer<typeof rotateAgentTokenSchema>;
export type IssuedAgentToken = z.infer<typeof issuedAgentTokenSchema>;
