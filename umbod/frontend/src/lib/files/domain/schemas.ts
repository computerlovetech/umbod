import { z } from 'zod';

export const nodeIdSchema = z.uuid();
const emptyObjectSchema = z.strictObject({});
export const metadataSchema = z.object({
  content_type: z.union([z.string(), emptyObjectSchema]),
  attributes: z.record(z.string(), z.string())
});
export const nodePermissionsSchema = z.strictObject({
  can_discover: z.boolean(),
  can_read: z.boolean(),
  can_write: z.boolean(),
  can_delete: z.boolean(),
  can_share: z.boolean()
});
export const nodePrincipalSchema = z.strictObject({
  type: z.enum(['user', 'group', 'system']),
  issuer: z.string(),
  id: z.string()
});
export const nodeGrantSchema = z.strictObject({
  node_id: nodeIdSchema,
  principal: nodePrincipalSchema,
  permissions: z.array(z.enum(['discover', 'read', 'write', 'delete', 'share'])),
  recursive: z.boolean()
});
export const nodeVisibilitySchema = z.discriminatedUnion('type', [
  z.strictObject({
    type: z.literal('available'),
    scope: z.literal('direct_node_policy'),
    owner: nodePrincipalSchema,
    grants: z.array(nodeGrantSchema),
    group_members_expanded: z.literal(false)
  }),
  z.strictObject({ type: z.literal('restricted') }),
  z.strictObject({ type: z.literal('unavailable') })
]);
export const nodeSummarySchema = z.strictObject({
  id: nodeIdSchema,
  parent_id: z.union([nodeIdSchema, emptyObjectSchema]),
  name: z.string(),
  kind: z.enum(['directory', 'file']),
  metadata: metadataSchema,
  permissions: nodePermissionsSchema,
  visible_to: nodeVisibilitySchema,
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
export const browseCapabilitiesSchema = z.strictObject({
  node_id: nodeIdSchema,
  rename: z.boolean(),
  move: z.boolean(),
  edit_description: z.boolean(),
  delete: z.boolean(),
  share: z.boolean(),
  upload: z.boolean(),
  create_directory: z.boolean()
});
export const browseResultSchema = z.strictObject({
  node: nodeSummarySchema,
  breadcrumbs: breadcrumbsSchema,
  entries: z.array(nodeSummarySchema),
  capabilities: z.array(browseCapabilitiesSchema),
  truncated: z.literal(false)
}).superRefine((result, context) => {
  const { node, breadcrumbs, entries, capabilities } = result;
  const last = breadcrumbs.items.at(-1);
  const ids = [node.id, ...entries.map((entry) => entry.id)];
  const capabilityIds = new Set(capabilities.map((capability) => capability.node_id));
  const invalid = last?.id !== node.id || last.name !== node.name || last.kind !== node.kind
    || new Set(breadcrumbs.items.map((item) => item.id)).size !== breadcrumbs.items.length
    || breadcrumbs.items.slice(0, -1).some((item) => item.kind !== 'directory')
    || breadcrumbs.complete && (breadcrumbs.items[0].kind !== 'directory' || breadcrumbs.items[0].name !== '')
    || node.kind === 'file' && entries.length !== 0
    || entries.some((entry) => entry.parent_id !== node.id)
    || new Set(ids).size !== ids.length
    || capabilityIds.size !== capabilities.length
    || capabilityIds.size !== ids.length
    || ids.some((id) => !capabilityIds.has(id));
  if (invalid) context.addIssue({ code: 'custom', message: 'Inconsistent filesystem browse result.' });
});
export type BrowseCapabilities = z.infer<typeof browseCapabilitiesSchema>;
export type BrowseResult = z.infer<typeof browseResultSchema>;
export type BreadcrumbItem = z.infer<typeof breadcrumbItemSchema>;
export type Breadcrumbs = z.infer<typeof breadcrumbsSchema>;
export const childrenSchema = z.strictObject({ nodes: z.array(nodeSummarySchema) });
export const fileNameSchema = z.string().min(1).refine((name) => name.trim().length > 0 && !name.includes('/') && !name.includes('\\') && !name.includes('\u0000') && name !== '.' && name !== '..', 'Enter a name without path separators.');
export const fileRevisionSchema = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
export const nodeCapabilitiesSchema = z.object({
  allow: z.string().transform((value) => value.split(',').map((method) => method.trim()))
    .pipe(z.array(z.string().regex(/^[!#$%&'*+.^_`|~0-9A-Z-]+$/)).nonempty())
    .refine((methods) => methods.includes('OPTIONS'))
}).transform((headers) => headers.allow);
export const updateDescriptionSchema = z.strictObject({ description: z.string() });
export type UpdateDescription = z.infer<typeof updateDescriptionSchema>;
export const updateNodeSchema = z.strictObject({
  name: fileNameSchema.optional(),
  parent_id: nodeIdSchema.optional(),
  metadata: z.strictObject({
    attributes: z.record(z.string(), z.string()).optional(),
    content_type: z.union([z.string(), emptyObjectSchema]).optional()
  }).refine((metadata) => metadata.content_type !== undefined || Object.keys(metadata.attributes ?? {}).length > 0, 'Provide a metadata change.').optional()
}).refine((input) => input.name !== undefined || input.parent_id !== undefined || input.metadata !== undefined, 'Provide a change.');
export type UpdateNode = z.infer<typeof updateNodeSchema>;
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
export const unavailableUploadTransferSchema = z.strictObject({
  type: z.literal('unavailable'),
  reason: z.enum(['expired', 'completed'])
});
export const uploadTransferSchema = z.discriminatedUnion('type', [singleUploadTransferSchema, unavailableUploadTransferSchema]);
export type SingleUploadTransfer = z.infer<typeof singleUploadTransferSchema>;
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
  name: fileNameSchema,
  description: z.string().optional()
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
