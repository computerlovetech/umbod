import { z } from 'zod';

export const dimensions = ['source', 'event_name', 'severity', 'session_id', 'tool_name'] as const;
export const dimensionSchema = z.enum(dimensions);
export type Dimension = z.infer<typeof dimensionSchema>;
const timestamp = z.iso.datetime({ offset: true });
export const logCountQuerySchema = z.strictObject({
  time_range: z.strictObject({ start: timestamp, end: timestamp }).refine((range) => Date.parse(range.start) < Date.parse(range.end), 'Start must be before end'),
  filters: z.array(z.strictObject({ dimension: dimensionSchema, values: z.array(z.string()).min(1).refine((values) => new Set(values).size === values.length, 'Filter values must be unique') })).max(5).refine((filters) => new Set(filters.map((filter) => filter.dimension)).size === filters.length, 'Filter dimensions must be unique'),
  group_by: z.array(dimensionSchema).max(5).refine((groups) => new Set(groups).size === groups.length, 'Grouping dimensions must be unique'),
  bucketing: z.discriminatedUnion('kind', [
    z.strictObject({ kind: z.literal('none') }),
    z.strictObject({ kind: z.literal('fixed'), width: z.enum(['minute', 'hour', 'day']) })
  ]),
  max_groups: z.number().int().min(1).max(1000)
});
export const logCountResponseSchema = z.strictObject({
  rows: z.array(z.strictObject({
    groups: z.array(z.strictObject({
      dimension: dimensionSchema,
      value: z.discriminatedUnion('kind', [
        z.strictObject({ kind: z.literal('missing') }),
        z.strictObject({ kind: z.literal('present'), value: z.string() })
      ])
    })).max(5).refine((groups) => new Set(groups.map((group) => group.dimension)).size === groups.length, 'Group dimensions must be unique'),
    count: z.number().int().nonnegative(),
    bucket: z.discriminatedUnion('kind', [
      z.strictObject({ kind: z.literal('none') }),
      z.strictObject({ kind: z.literal('bucket'), start: timestamp })
    ])
  })).max(1000)
});
export type LogCountQuery = z.infer<typeof logCountQuerySchema>;
export type LogCountResponse = z.infer<typeof logCountResponseSchema>;
