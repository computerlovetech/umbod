import { z } from 'zod';

export const identifierSchema = z.string().regex(/^[a-z][a-z0-9-]{0,63}$/);
const bounded = (maximum: number): z.ZodString => z.string().refine((value): boolean => Array.from(value).length <= maximum, `Must contain at most ${maximum} characters`);
const text = (maximum: number): z.ZodString => bounded(maximum).trim().min(1);
const identifiers = (maximum: number): z.ZodArray<typeof identifierSchema> => z.array(identifierSchema).max(maximum).refine((values): boolean => new Set(values).size === values.length);
export const patternSchema = z.strictObject({ id: identifierSchema, name: text(120), description: text(2000), assessment_prompt: text(4000), inclusion_criteria: bounded(4000), exclusion_criteria: bounded(4000), categories: identifiers(10), polarity: z.enum(['positive', 'negative', 'neutral']), enabled: z.boolean() });
export const playbookSchema = z.strictObject({ id: identifierSchema, name: text(120), collection_instructions: text(8000), pattern_ids: identifiers(20).min(1), enabled: z.boolean(), allow_proactive: z.boolean() });
const collections = { patterns: z.array(patternSchema).max(50), playbooks: z.array(playbookSchema).max(20) };
export const configurationSchema = z.strictObject({ revision: z.number().int().nonnegative(), ...collections });
export const publishSchema = z.strictObject({ expected_revision: z.number().int().nonnegative(), ...collections }).superRefine((value, context): void => {
  for (const key of ['patterns', 'playbooks'] as const) {
    if (new Set(value[key].map((item): string => item.id)).size !== value[key].length) context.addIssue({ code: 'custom', path: [key], message: 'IDs must be unique' });
  }

});
export const statusSchema = z.enum(['observed', 'not_observed', 'not_assessed']);
const callerSchema = z.strictObject({ authentication: z.enum(['upstream_verified', 'deployment_authenticated', 'local_simulation', 'local_semantic', 'local_test', 'unavailable']), subject: z.union([z.strictObject({ issuer: z.union([z.strictObject({ value: z.string() }), z.strictObject({ kind: z.literal('unavailable') })]), subject: z.string() }), z.strictObject({ kind: z.literal('unavailable') })]) });
const reportFields = { report_id: z.uuid(), received_at: z.iso.datetime({ offset: true }), expires_at: z.iso.datetime({ offset: true }), caller: callerSchema };
export const summarySchema = z.strictObject({ ...reportFields, playbook_id: identifierSchema, configuration_revision: z.number().int().nonnegative(), trigger: z.enum(['user_requested', 'proactive']), observed_pattern_ids: z.array(identifierSchema) });
export const reportSchema = z.strictObject({ ...reportFields, submission: z.strictObject({ idempotency_key: z.uuid(), configuration_revision: z.number().int().positive(), playbook_id: identifierSchema, trigger: z.enum(['user_requested', 'proactive']), assessments: z.array(z.strictObject({ pattern_id: identifierSchema, status: statusSchema, summary: bounded(1000), evidence: z.array(text(500)).max(3) })).min(1).max(20) }), instructions: z.strictObject({ configuration_revision: z.number().int().positive(), playbook: playbookSchema, patterns: z.array(patternSchema), reporting_guidance: z.string(), resource_uri: z.string() }) });
export const pageSchema = z.strictObject({ items: z.array(summarySchema), total: z.number().int().nonnegative() });
export const querySchema = z.strictObject({ limit: z.number().int().min(1).max(100), offset: z.number().int().nonnegative(), playbook_id: identifierSchema.optional(), pattern_id: identifierSchema.optional(), status: statusSchema.optional() });
export const conflictSchema = z.object({ detail: z.strictObject({ code: z.literal('revision_conflict'), current: configurationSchema }) });
export type BehaviourPattern = z.infer<typeof patternSchema>;
export type DiagnosticPlaybook = z.infer<typeof playbookSchema>;
export type Configuration = z.infer<typeof configurationSchema>;
export type PublishConfiguration = z.infer<typeof publishSchema>;
export type ReportQuery = z.infer<typeof querySchema>;
export type ReportPage = z.infer<typeof pageSchema>;
export type DiagnosticReport = z.infer<typeof reportSchema>;
