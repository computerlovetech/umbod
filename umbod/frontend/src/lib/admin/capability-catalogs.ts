import { z } from 'zod';

const activationStatusSchema = z.enum(['enabled', 'disabled']);
const nativePromptAvailableActionSchema = z.enum(['activate']);
const nativeResourceAvailableActionSchema = z.enum(['activate']);
const promptAvailableActionSchema = z.enum(['activate', 'invoke_prompt', 'edit']);
const resourceAvailableActionSchema = z.enum(['activate', 'read_resource', 'edit']);

export const promptArgumentSchema = z.object({
  name: z.string(),
  description: z.string(),
  required: z.boolean()
}).strict();

export const promptSchema = z.object({
  name: z.string(),
  description: z.string(),
  arguments: z.array(promptArgumentSchema),
  activation_status: activationStatusSchema
}).strict();

const resourceWireSchema = z.object({
  kind: z.enum(['resource', 'resource_template']),
  name: z.string(),
  description: z.string(),
  uri: z.string(),
  activation_status: activationStatusSchema
}).strict();

export const promptCatalogSchema = z.object({
  prompts: z.array(promptSchema),
  available_actions: z.array(nativePromptAvailableActionSchema)
}).strict();

export const resourceCatalogWireSchema = z.object({
  resources: z.array(resourceWireSchema),
  available_actions: z.array(nativeResourceAvailableActionSchema)
}).strict();

export const downstreamPromptCatalogSchema = z.object({
  prompts: z.array(promptSchema),
  available_actions: z.array(promptAvailableActionSchema)
}).strict();

export const downstreamResourceCatalogWireSchema = z.object({
  resources: z.array(resourceWireSchema),
  available_actions: z.array(resourceAvailableActionSchema)
}).strict();

export const resourceSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('resource'),
    name: z.string(),
    description: z.string(),
    uri: z.string(),
    activationStatus: activationStatusSchema
  }).strict(),
  z.object({
    kind: z.literal('resource_template'),
    name: z.string(),
    description: z.string(),
    uriTemplate: z.string(),
    activationStatus: activationStatusSchema
  }).strict()
]);

export const resourceCatalogSchema = z.object({
  resources: z.array(resourceSchema),
  availableActions: z.array(resourceAvailableActionSchema)
}).strict();

export type PromptCatalog = {
  prompts: z.infer<typeof promptSchema>[];
  available_actions: z.infer<typeof promptAvailableActionSchema>[];
};
export type ResourceCatalog = z.infer<typeof resourceCatalogSchema>;
export type ResourceCatalogWire = z.infer<typeof resourceCatalogWireSchema>;

type ResourceCatalogWireInput = {
  resources: z.infer<typeof resourceWireSchema>[];
  available_actions: ReadonlyArray<z.infer<typeof resourceAvailableActionSchema>>;
};

export function mapResourceCatalog(catalog: ResourceCatalogWireInput): ResourceCatalog {
  return {
    resources: catalog.resources.map((resource) =>
      resource.kind === 'resource'
        ? {
            kind: 'resource' as const,
            name: resource.name,
            description: resource.description,
            uri: resource.uri,
            activationStatus: resource.activation_status
          }
        : {
            kind: 'resource_template' as const,
            name: resource.name,
            description: resource.description,
            uriTemplate: resource.uri,
            activationStatus: resource.activation_status
          }
    ),
    availableActions: [...catalog.available_actions]
  };
}

export const promptActivationBatchRequestSchema = z.object({
  prompts: z.array(z.object({
    prompt_id: z.string().min(1),
    activation_status: activationStatusSchema
  }).strict()).min(1)
}).strict();

export const promptActivationBatchResponseSchema = z.object({
  connector_id: z.string().min(1),
  prompts: z.array(z.object({
    prompt_id: z.string().min(1),
    activation_status: activationStatusSchema
  }).strict())
}).strict();

export const resourceActivationBatchRequestSchema = z.object({
  resources: z.array(z.object({
    resource_id: z.string().min(1),
    kind: z.enum(['resource', 'resource_template']),
    activation_status: activationStatusSchema
  }).strict()).min(1)
}).strict();

export const resourceActivationBatchResponseSchema = z.object({
  connector_id: z.string().min(1),
  resources: z.array(z.object({
    resource_id: z.string().min(1),
    kind: z.enum(['resource', 'resource_template']),
    activation_status: activationStatusSchema
  }).strict())
}).strict();

export type PromptActivationBatchRequest = z.infer<typeof promptActivationBatchRequestSchema>;
export type PromptActivationBatchResponse = z.infer<typeof promptActivationBatchResponseSchema>;
export type ResourceActivationBatchRequest = z.infer<typeof resourceActivationBatchRequestSchema>;
export type ResourceActivationBatchResponse = z.infer<typeof resourceActivationBatchResponseSchema>;
export type CapabilityActivationStatus = z.infer<typeof activationStatusSchema>;

export function resourceActivationKey(
  kind: 'resource' | 'resource_template',
  resourceId: string
): string {
  return `${kind}:${resourceId}`;
}

export function emptyPromptCatalog(): PromptCatalog {
  return { prompts: [], available_actions: [] };
}

export function emptyResourceCatalog(): ResourceCatalog {
  return { resources: [], availableActions: [] };
}
