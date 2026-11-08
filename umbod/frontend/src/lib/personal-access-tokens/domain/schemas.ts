import { z } from 'zod';

const boundedText = z.string().min(1).max(256).refine((value: string): boolean => value.trim().length > 0);
const timestamp = z.iso.datetime({ offset: true });
const ownerText = z.string().min(1).max(4096).refine((value: string): boolean => value.trim().length > 0);
const scope = z.string().min(1).max(128).regex(/^[^\s*]+$/);
export const tokenIdSchema = z.string().regex(/^[0-9a-f]{32}$/);
export const tokenMetadataSchema = z.strictObject({
  token_id: tokenIdSchema,
  owner: z.strictObject({ issuer: ownerText, subject: ownerText }),
  name: boundedText,
  audience: boundedText,
  scopes: z.array(scope).min(1).max(64).refine((values: string[]): boolean => new Set(values).size === values.length),
  created_at: timestamp,
  expires_at: timestamp,
  status: z.enum(['active', 'revoked'])
}).refine((value): boolean => Date.parse(value.expires_at) > Date.parse(value.created_at));
export const createTokenSchema = z.strictObject({
  name: boundedText,
  expires_at: timestamp.refine((value: string): boolean => Date.parse(value) > Date.now()),
  permissions: z.strictObject({ telemetry: z.literal('write') })
});
export const createdTokenSchema = z.strictObject({ metadata: tokenMetadataSchema, token: z.string().min(1) });
export const tokenListSchema = z.array(tokenMetadataSchema);
export type TokenMetadata = z.infer<typeof tokenMetadataSchema>;
export type CreateToken = z.infer<typeof createTokenSchema>;
export type CreatedToken = z.infer<typeof createdTokenSchema>;
