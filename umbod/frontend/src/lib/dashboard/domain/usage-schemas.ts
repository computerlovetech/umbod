import { z } from 'zod';

export const usageDaysSchema = z.union([z.literal(7), z.literal(30)]);
export type UsageDays = z.infer<typeof usageDaysSchema>;
export const usageCategories = ['tool', 'resource', 'prompt'] as const;
export const usageOutcomes = ['success', 'failure', 'cancelled'] as const;

const outcomesSchema = z.strictObject({
  success: z.number().int().nonnegative(),
  failure: z.number().int().nonnegative(),
  cancelled: z.number().int().nonnegative()
}).readonly();

const countsSchema = z.strictObject({
  tool: outcomesSchema,
  resource: outcomesSchema,
  prompt: outcomesSchema
}).readonly();

export const personalUsageSchema = z.strictObject({
  identity_key: z.string().min(1),
  range: z.strictObject({ start: z.iso.date(), end: z.iso.date(), timezone: z.literal('UTC') }).readonly(),
  as_of: z.iso.datetime({ offset: true }).refine((value) => value.endsWith('Z') || value.endsWith('+00:00')),
  totals: countsSchema,
  daily: z.array(z.strictObject({ date: z.iso.date(), counts: countsSchema }).readonly()).readonly()
}).superRefine((usage, context): void => {
  const start = Date.parse(usage.range.start);
  const days = (Date.parse(usage.range.end) - start) / 86400000;
  const today = Date.parse(usage.as_of.slice(0, 10));
  const datesValid = (days === 7 || days === 30) && usage.daily.length === days
    && Date.parse(usage.range.end) === today + 86400000
    && usage.daily.every((row, index) => Date.parse(row.date) === start + index * 86400000);
  const totalsValid = usageCategories.every((category) => usageOutcomes.every((outcome) =>
    usage.totals[category][outcome] === usage.daily.reduce((sum, row) => sum + row.counts[category][outcome], 0)));
  if (!datesValid || !totalsValid) context.addIssue({ code: 'custom', message: 'Invalid usage snapshot' });
}).readonly();

export type PersonalUsage = z.infer<typeof personalUsageSchema>;
export type UsageCounts = z.infer<typeof countsSchema>;
