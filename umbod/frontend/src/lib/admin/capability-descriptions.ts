import { z } from 'zod';

export const connectorKindSchema = z.enum(['native', 'downstream_mcp', 'openapi']);
export const capabilityDescriptionSchema = z.string().trim().min(1).max(300).refine((value) => !/[\u0000-\u001f\u007f]/.test(value), 'Control characters are not allowed');
const revisionSchema = z.number().int().nonnegative();
export const capabilityDescriptionOverrideSchema = z.discriminatedUnion('state', [
  z.object({ state: z.literal('system'), revision: revisionSchema }).strict(),
  z.object({ state: z.literal('overridden'), description: capabilityDescriptionSchema, revision: revisionSchema.min(1) }).strict()
]);
export const capabilityDescriptionResponseSchema = z.object({
  connector_kind: connectorKindSchema,
  connector_id: z.string().min(1),
  base_description: capabilityDescriptionSchema,
  effective_description: capabilityDescriptionSchema,
  override: capabilityDescriptionOverrideSchema
}).strict();
export const setCapabilityDescriptionRequestSchema = z.object({ action: z.literal('set'), description: capabilityDescriptionSchema, expected_revision: revisionSchema }).strict();
export const clearCapabilityDescriptionRequestSchema = z.object({ action: z.literal('clear'), expected_revision: revisionSchema }).strict();
export const revisionConflictEnvelopeSchema = z.object({ detail: z.object({ code: z.literal('capability_description_revision_conflict'), current: capabilityDescriptionResponseSchema }).strict() }).strict();

export type ConnectorKind = z.infer<typeof connectorKindSchema>;
export type CapabilityDescriptionResponse = z.infer<typeof capabilityDescriptionResponseSchema>;

export class CapabilityDescriptionConflictError extends Error {
  constructor(readonly current: CapabilityDescriptionResponse) {
    super('Capability description changed');
    this.name = 'CapabilityDescriptionConflictError';
  }
}
