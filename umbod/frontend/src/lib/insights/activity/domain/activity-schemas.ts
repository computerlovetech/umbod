import { z } from 'zod';
import { usageDaysSchema, usageSummarySchema } from '#lib/usage/usage-schemas.js';

export const activityDaysSchema = usageDaysSchema;
export type ActivityDays = z.infer<typeof activityDaysSchema>;

const utcDateTimeSchema = z.iso.datetime({ offset: true }).refine(
  (value): boolean => value.endsWith('Z') || value.endsWith('+00:00'),
  'Expected a UTC timestamp'
);

const activityPeriodSchema = z.strictObject({
  days: activityDaysSchema,
  as_of: utcDateTimeSchema,
  window: z.strictObject({ start: utcDateTimeSchema, end: utcDateTimeSchema }).readonly()
}).refine(({ days, as_of, window }): boolean => {
  const dayMilliseconds = 86_400_000;
  const end = Date.parse(as_of.slice(0, 10)) + dayMilliseconds;
  return Date.parse(window.end) === end && Date.parse(window.start) === end - days * dayMilliseconds;
}, 'Expected a UTC calendar window including the as_of date').readonly();

const nonnegativeCountSchema = z.number().int().nonnegative();

const harnessOutcomesSchema = z.strictObject({
  success: nonnegativeCountSchema,
  failure: nonnegativeCountSchema,
  unknown: nonnegativeCountSchema
}).readonly();

const rankedToolSchema = z.strictObject({
  tool_name: z.string().min(1),
  count: z.number().int().positive()
}).readonly();

const topToolsSchema = z.array(rankedToolSchema).max(5).readonly();

const harnessSummarySchema = z.strictObject({
  outcomes: harnessOutcomesSchema,
  top_tools: topToolsSchema,
  skill_activations: nonnegativeCountSchema
}).readonly();

const unavailableSchema = z.strictObject({ status: z.literal('unavailable') }).readonly();
const harnessAvailableSchema = z.strictObject({ status: z.literal('available'), summary: harnessSummarySchema }).readonly();
const mcpAvailableSchema = z.strictObject({ status: z.literal('available'), summary: usageSummarySchema }).readonly();

const identityKeySchema = z.string().min(1);

const activityOverviewShape = z.strictObject({
  identity_key: identityKeySchema,
  period: activityPeriodSchema,
  harness: z.discriminatedUnion('status', [harnessAvailableSchema, unavailableSchema]),
  mcp: z.discriminatedUnion('status', [mcpAvailableSchema, unavailableSchema])
});

function canonicalUtcTimestamp(value: string): string {
  return value.replace(/\+00:00$/, 'Z').replace(/(\.\d*?)0+Z$/, '$1Z').replace(/\.Z$/, 'Z');
}

export const activityOverviewSchema = activityOverviewShape.refine(({ period, mcp }): boolean => {
  if (mcp.status === 'unavailable') return true;
  const { range, as_of } = mcp.summary;
  return range.start === period.window.start.slice(0, 10)
    && range.end === period.window.end.slice(0, 10)
    && canonicalUtcTimestamp(as_of) === canonicalUtcTimestamp(period.as_of);
}, 'Expected the MCP summary to cover the Activity period').readonly();
export const unavailableActivityOverviewSchema = activityOverviewShape.extend({
  harness: unavailableSchema,
  mcp: unavailableSchema
}).readonly();

export type ActivityOverview = z.infer<typeof activityOverviewSchema>;
export type HarnessActivitySummary = z.infer<typeof harnessSummarySchema>;

export const harnessSourceSchema = z.enum(['claude-code', 'claude-code-desktop', 'codex', 'codex_exec']);
export type HarnessSource = z.infer<typeof harnessSourceSchema>;

const sessionIdSchema = z.string().refine((value): boolean =>
  Array.from(value).length <= 1024 && /[^\p{White_Space}\u001c-\u001f]/u.test(value)
  && !/[\u0000\p{Surrogate}]/u.test(value) && value !== '.' && value !== '..',
'Expected a URL-safe, nonblank session ID of up to 1,024 characters');

export const activitySessionKeySchema = z.strictObject({
  source: harnessSourceSchema,
  session_id: sessionIdSchema
}).readonly();

export type ActivitySessionKey = z.infer<typeof activitySessionKeySchema>;

const cursorSchema = z.string().min(1).refine((value): boolean => Array.from(value).length <= 16_384);

export const activitySessionsQuerySchema = z.strictObject({
  days: activityDaysSchema.optional(),
  q: z.string().refine((value): boolean => Array.from(value).length <= 128).optional(),
  cursor: cursorSchema.optional(),
  limit: z.number().int().min(1).max(100).optional()
}).readonly();

export type ActivitySessionsQuery = z.infer<typeof activitySessionsQuerySchema>;

const sessionSummarySchema = z.strictObject({
  key: activitySessionKeySchema,
  first_seen_at: utcDateTimeSchema,
  last_seen_at: utcDateTimeSchema,
  outcomes: harnessOutcomesSchema
}).readonly();

export const activitySessionPageSchema = z.strictObject({
  identity_key: identityKeySchema,
  period: activityPeriodSchema,
  sessions: z.array(sessionSummarySchema).max(100).refine(
    (sessions): boolean => new Set(sessions.map(({ key }): string => JSON.stringify([key.source, key.session_id]))).size === sessions.length,
    'Expected distinct session keys'
  ).readonly(),
  page: z.discriminatedUnion('kind', [
    z.strictObject({ kind: z.literal('more'), cursor: cursorSchema }).readonly(),
    z.strictObject({ kind: z.literal('end') }).readonly()
  ])
}).readonly();

export const activitySessionReportSchema = z.strictObject({
  identity_key: identityKeySchema,
  session: sessionSummarySchema,
  top_tools: topToolsSchema,
  failed_tools: z.array(rankedToolSchema).max(100).readonly(),
  has_more_failed_tools: z.boolean(),
  skill_activations: nonnegativeCountSchema
}).readonly();

export type ActivitySessionSummary = z.infer<typeof sessionSummarySchema>;
export type ActivitySessionPage = z.infer<typeof activitySessionPageSchema>;
export type ActivitySessionReport = z.infer<typeof activitySessionReportSchema>;
