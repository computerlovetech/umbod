import { z } from 'zod';

export const invocationPolicyModeSchema = z.enum(['direct', 'ask']);
export const invocationPolicyToolSchema = z.object({
  tool_id: z.string().min(1),
  mode: invocationPolicyModeSchema,
  revision: z.number().int().nonnegative()
});
export const invocationPolicyListResponseSchema = z.object({
  connector_kind: z.enum(['native', 'openapi', 'downstream_mcp']),
  connector_id: z.string().min(1),
  tools: z.array(invocationPolicyToolSchema)
});
export const invocationPolicyUpdateToolSchema = z.object({
  tool_id: z.string().min(1),
  mode: invocationPolicyModeSchema,
  expected_revision: z.number().int().nonnegative()
});
export const invocationPolicyBatchUpdateRequestSchema = z.object({
  tools: z.array(invocationPolicyUpdateToolSchema).min(1).superRefine((tools, context) => {
    const seen = new Set<string>();
    tools.forEach((tool, index) => {
      if (seen.has(tool.tool_id)) context.addIssue({ code: 'custom', message: 'Tool IDs must be unique', path: [index, 'tool_id'] });
      seen.add(tool.tool_id);
    });
  })
});
export const invocationPolicyConflictSchema = z.object({
  tool_id: z.string().min(1),
  expected_revision: z.number().int().nonnegative(),
  current_mode: invocationPolicyModeSchema,
  current_revision: z.number().int().nonnegative()
});
export const invocationPolicyConflictResponseSchema = z.object({
  code: z.literal('invocation_policy_revision_conflict'),
  conflicts: z.array(invocationPolicyConflictSchema)
});

export type InvocationPolicyMode = z.infer<typeof invocationPolicyModeSchema>;
export type InvocationPolicyTool = z.infer<typeof invocationPolicyToolSchema>;
export type InvocationPolicyListResponse = z.infer<typeof invocationPolicyListResponseSchema>;
export type InvocationPolicyBatchUpdateRequest = z.infer<typeof invocationPolicyBatchUpdateRequestSchema>;
