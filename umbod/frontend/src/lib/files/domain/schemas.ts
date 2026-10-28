import { z } from 'zod';

export const nodeIdSchema = z.uuid();
const emptyObjectSchema = z.strictObject({});
export const metadataSchema = z.object({
  content_type: z.union([z.string(), emptyObjectSchema]),
  attributes: z.record(z.string(), z.string())
});
export const nodeSummarySchema = z.strictObject({
  id: nodeIdSchema,
  parent_id: z.union([nodeIdSchema, emptyObjectSchema]),
  name: z.string(),
  kind: z.enum(['directory', 'file']),
  metadata: metadataSchema,
  created_at: z.iso.datetime({ offset: true, local: true }),
  updated_at: z.iso.datetime({ offset: true, local: true }),
  revision: z.number().int().min(1)
});
export const childrenSchema = z.strictObject({ nodes: z.array(nodeSummarySchema) });
export const fileNameSchema = z.string().min(1).refine((name) => name.trim().length > 0 && !name.includes('/') && !name.includes('\\') && !name.includes('\u0000') && name !== '.' && name !== '..', 'Enter a name without path separators.');
export const uploadPolicySchema = z.strictObject({ max_bytes: z.number().int().positive() });
export const fileUploadSchema = z.strictObject({
  file: z.custom<File>((value) => typeof File !== 'undefined' && value instanceof File, 'Select a file.'),
  name: fileNameSchema
});
export const createFolderSchema = z.strictObject({
  name: fileNameSchema,
  metadata: z.strictObject({ content_type: emptyObjectSchema, attributes: z.record(z.string(), z.string()) })
});
export type NodeSummary = z.infer<typeof nodeSummarySchema>;
export type CreateFolder = z.infer<typeof createFolderSchema>;
export type UploadPolicy = z.infer<typeof uploadPolicySchema>;
export type FileUpload = z.infer<typeof fileUploadSchema>;
