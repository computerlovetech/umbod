import { z } from "zod";

export const instanceConfigurationValueTypeSchema = z.enum([
  "string",
  "integer",
  "number",
  "boolean",
  "string_list",
]);

const valueByType = {
  string: z.string(),
  integer: z.number().int(),
  number: z.number(),
  boolean: z.boolean(),
  string_list: z.array(z.string()),
} as const;

export const instanceConfigurationEntrySchema = z.discriminatedUnion("type", [
  z.object({
    variable: z.string(),
    label: z.string(),
    description: z.string(),
    type: z.literal("string"),
    value: valueByType.string,
  }),
  z.object({
    variable: z.string(),
    label: z.string(),
    description: z.string(),
    type: z.literal("integer"),
    value: valueByType.integer,
  }),
  z.object({
    variable: z.string(),
    label: z.string(),
    description: z.string(),
    type: z.literal("number"),
    value: valueByType.number,
  }),
  z.object({
    variable: z.string(),
    label: z.string(),
    description: z.string(),
    type: z.literal("boolean"),
    value: valueByType.boolean,
  }),
  z.object({
    variable: z.string(),
    label: z.string(),
    description: z.string(),
    type: z.literal("string_list"),
    value: valueByType.string_list,
  }),
]);

export const instanceConfigurationSchema = z.object({
  groups: z.array(
    z.object({
      id: z.string(),
      label: z.string(),
      entries: z.array(instanceConfigurationEntrySchema),
    }),
  ),
});

export type InstanceConfiguration = z.infer<typeof instanceConfigurationSchema>;
export type InstanceConfigurationEntry = z.infer<
  typeof instanceConfigurationEntrySchema
>;

export type InstanceConfigurationPageData =
  | { status: "ready"; configuration: InstanceConfiguration }
  | { status: "empty" }
  | { status: "failed"; message: string; retryLabel: string };
