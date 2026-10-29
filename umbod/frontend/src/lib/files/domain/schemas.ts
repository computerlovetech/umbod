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
export const breadcrumbItemSchema = z.strictObject({
  id: nodeIdSchema,
  name: z.string(),
  kind: z.enum(['directory', 'file'])
});
export const breadcrumbsSchema = z.strictObject({
  items: z.array(breadcrumbItemSchema).nonempty(),
  complete: z.boolean()
});
export type BreadcrumbItem = z.infer<typeof breadcrumbItemSchema>;
export type Breadcrumbs = z.infer<typeof breadcrumbsSchema>;
export const childrenSchema = z.strictObject({ nodes: z.array(nodeSummarySchema) });
export const fileNameSchema = z.string().min(1).refine((name) => name.trim().length > 0 && !name.includes('/') && !name.includes('\\') && !name.includes('\u0000') && name !== '.' && name !== '..', 'Enter a name without path separators.');
export const fileRevisionSchema = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
export const deleteEligibilitySchema = z.object({
  allow: z.string().refine((value) => value.split(',').some((method) => method.trim() === 'DELETE'))
}).transform(() => undefined);
export const uploadEligibilitySchema = z.object({
  allow: z.string().refine((value) => value.split(',').some((method) => method.trim() === 'POST'))
}).transform(() => undefined);
export const uploadAuthorizationSchema = z.discriminatedUnion('type', [
  z.strictObject({ type: z.literal('same_origin') }),
  z.strictObject({ type: z.literal('none') })
]);
export const uploadHeadersSchema = z.record(
  z.string().regex(/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/),
  z.string().regex(/^[^\r\n]*$/)
).refine((headers) => Object.entries(headers).some(([name, value]) => name.toLowerCase() === 'content-type' && value.trim().length > 0), 'Content-Type is required.');
export const singleUploadTransferSchema = z.strictObject({
  type: z.literal('single'),
  method: z.literal('PUT'),
  url: z.string().min(1),
  headers: uploadHeadersSchema,
  authorization: uploadAuthorizationSchema
});
export const uploadTransferSchema = z.discriminatedUnion('type', [singleUploadTransferSchema]);
export const beginUploadSchema = z.strictObject({
  name: fileNameSchema,
  metadata: z.strictObject({ content_type: z.string().min(1), attributes: z.record(z.string(), z.string()) }),
  size_bytes: z.number().int().nonnegative()
});
export const uploadSessionSchema = z.strictObject({
  id: nodeIdSchema,
  expires_at: z.iso.datetime({ offset: true }),
  status: z.enum(['pending', 'uploaded', 'completed']),
  transfer: uploadTransferSchema,
  complete_url: z.string().min(1)
});
export const rawUploadSchema = z.custom<File>((value) => typeof File !== 'undefined' && value instanceof File, 'Select a file.');
export const fileUploadSchema = z.strictObject({
  file: rawUploadSchema,
  name: fileNameSchema
});
export const createFolderSchema = z.strictObject({
  name: fileNameSchema,
  metadata: z.strictObject({ content_type: emptyObjectSchema, attributes: z.record(z.string(), z.string()) })
});
export type NodeSummary = z.infer<typeof nodeSummarySchema>;
export type CreateFolder = z.infer<typeof createFolderSchema>;
export type BeginUpload = z.infer<typeof beginUploadSchema>;
export type UploadSession = z.infer<typeof uploadSessionSchema>;
export type UploadTransfer = z.infer<typeof uploadTransferSchema>;
export type FileUpload = z.infer<typeof fileUploadSchema>;
