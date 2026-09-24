import { z } from 'zod';
import { nullishOptional } from './infrastructure/schema';

export const capabilityKindSchema = z.enum(['tool', 'prompt', 'resource', 'resource_template']);
export type CapabilityKind = z.infer<typeof capabilityKindSchema>;

export const apiGroupPermissionCapabilitySchema = z.object({
  connector_id: z.string(),
  capability_kind: capabilityKindSchema,
  capability_key: z.string()
});

export const apiGroupPermissionSetSchema = z.object({
  group_id: z.string(),
  connector_ids: z.array(z.string()),
  capabilities: z.array(apiGroupPermissionCapabilitySchema)
});

export const apiGroupPermissionSummarySchema = z.object({
  group_id: z.string()
});

export const apiGroupPermissionsResponseSchema = z.object({
  groups: z.array(apiGroupPermissionSummarySchema)
});

export const apiAssignableConnectorSchema = z.object({
  connector_id: z.string(),
  display_name: z.string(),
  description: nullishOptional(z.string())
});

export const apiAssignableCapabilitySchema = z.object({
  connector_id: z.string(),
  capability_kind: capabilityKindSchema,
  capability_key: z.string(),
  display_name: z.string(),
  description: nullishOptional(z.string())
});

export const apiAssignableTargetsResponseSchema = z.object({
  connectors: z.array(apiAssignableConnectorSchema),
  capabilities: z.array(apiAssignableCapabilitySchema)
});

const permissionStatusSchema = z.enum(['enabled', 'disabled']);
const connectorPermissionUpdateSchema = z.strictObject({
  connector_id: z.string().trim().min(1),
  permission_status: permissionStatusSchema
});
const capabilityPermissionUpdateSchema = z.strictObject({
  connector_id: z.string().trim().min(1),
  capability_kind: capabilityKindSchema,
  capability_key: z.string().trim().min(1),
  permission_status: permissionStatusSchema
});

export const updateGroupPermissionsRequestSchema = z.strictObject({
  connectors: z.array(connectorPermissionUpdateSchema).default([]),
  capabilities: z.array(capabilityPermissionUpdateSchema).default([])
}).superRefine((request, context) => {
  if (request.connectors.length === 0 && request.capabilities.length === 0) {
    context.addIssue({ code: 'custom', message: 'At least one permission change is required' });
  }
  const connectorIds = request.connectors.map((connector) => connector.connector_id);
  if (new Set(connectorIds).size !== connectorIds.length) {
    context.addIssue({ code: 'custom', message: 'Connector permission targets must be unique' });
  }
  const capabilityIds = request.capabilities.map(
    (capability) => `${capability.connector_id}\u0000${capability.capability_kind}\u0000${capability.capability_key}`
  );
  if (new Set(capabilityIds).size !== capabilityIds.length) {
    context.addIssue({ code: 'custom', message: 'Capability permission targets must be unique' });
  }
});

export const updateGroupPermissionsResponseSchema = z.object({
  status: z.string(),
  group_id: nullishOptional(z.string()),
  message: nullishOptional(z.string()),
  clients_notified: z.boolean().optional()
});

export type ApiGroupPermissionSet = z.infer<typeof apiGroupPermissionSetSchema>;
export type ApiGroupPermissionSummary = z.infer<typeof apiGroupPermissionSummarySchema>;
export type ApiGroupPermissionsResponse = z.infer<typeof apiGroupPermissionsResponseSchema>;
export type ApiAssignableTargetsResponse = z.infer<typeof apiAssignableTargetsResponseSchema>;
export type UpdateGroupPermissionsRequest = z.infer<typeof updateGroupPermissionsRequestSchema>;
export type UpdateGroupPermissionsResponse = z.infer<typeof updateGroupPermissionsResponseSchema>;

export const groupPermissionCapabilityRefSchema = z.object({
  connectorId: z.string(),
  kind: capabilityKindSchema,
  key: z.string()
});

export const groupPermissionSummarySchema = z.object({
  groupId: z.string()
});

export const groupPermissionSetSchema = z.object({
  groupId: z.string(),
  connectorIds: z.array(z.string()),
  capabilities: z.array(groupPermissionCapabilityRefSchema)
});

export const connectorCapabilitySchema = z.object({
  kind: capabilityKindSchema,
  key: z.string(),
  label: z.string(),
  description: z.string()
});

export const connectorPermissionTargetSchema = z.object({
  id: z.string(),
  displayName: z.string(),
  description: z.string(),
  capabilities: z.array(connectorCapabilitySchema)
});

export type GroupPermissionCapabilityRef = z.infer<typeof groupPermissionCapabilityRefSchema>;
export type GroupPermissionToolRef = { connectorId: string; operationName: string };
export type GroupPermissionSummary = z.infer<typeof groupPermissionSummarySchema>;
export type GroupPermissionSet = z.infer<typeof groupPermissionSetSchema>;
export type ConnectorCapability = z.infer<typeof connectorCapabilitySchema>;
export type ConnectorTool = { operationName: string; label: string; description: string };
export type ConnectorPermissionTarget = z.infer<typeof connectorPermissionTargetSchema>;

export type GroupPermissionsInitialTarget = {
  connectorId: string;
  operationId: string;
};

export type GroupPermissionsPageData = {
  status: 'ready';
  groups: GroupPermissionSummary[];
  preloadedGroup: GroupPermissionSet | null;
  assignableTargets: ConnectorPermissionTarget[];
  exactMatchGuidance: string;
  initialTarget: GroupPermissionsInitialTarget | null;
  originHref: string | null;
};

export type GroupPermissionsActionResult =
  | { status: 'saved'; groupId: string }
  | { status: 'registered'; groupId: string }
  | { status: 'deleted'; groupId: string }
  | { status: 'rejected'; groupId: string; message: string }
  | { status: 'failed'; groupId: string; message: string };

export type SaveGroupPermissionsResult = GroupPermissionsActionResult;

export const exactMatchGuidance =
  'JWT group values must exactly match the configured group value, including case and punctuation.';

export const capabilityKindSections: ReadonlyArray<{ kind: CapabilityKind; label: string }> = [
  { kind: 'tool', label: 'Tools' },
  { kind: 'prompt', label: 'Prompts' },
  { kind: 'resource', label: 'Resources' },
  { kind: 'resource_template', label: 'Resource templates' }
];

export function capabilityPermissionId(capability: GroupPermissionCapabilityRef): string {
  return `${capability.connectorId}\u0000${capability.kind}\u0000${capability.key}`;
}

export function mapGroupPermissionSummary(group: ApiGroupPermissionSummary): GroupPermissionSummary {
  return { groupId: group.group_id };
}

export function mapGroupPermissionSet(group: ApiGroupPermissionSet): GroupPermissionSet {
  return {
    groupId: group.group_id,
    connectorIds: group.connector_ids,
    capabilities: group.capabilities.map((capability) => ({
      connectorId: capability.connector_id,
      kind: capability.capability_kind,
      key: capability.capability_key
    }))
  };
}

export function mapAssignableTargets(targets: ApiAssignableTargetsResponse): ConnectorPermissionTarget[] {
  const capabilitiesByConnectorId = new Map<string, ConnectorCapability[]>();

  for (const capability of targets.capabilities) {
    const capabilities = capabilitiesByConnectorId.get(capability.connector_id) ?? [];
    capabilities.push({
      kind: capability.capability_kind,
      key: capability.capability_key,
      label: capability.display_name,
      description: capability.description ?? ''
    });
    capabilitiesByConnectorId.set(capability.connector_id, capabilities);
  }

  return targets.connectors.map((connector) => ({
    id: connector.connector_id,
    displayName: connector.display_name,
    description: connector.description ?? '',
    capabilities: capabilitiesByConnectorId.get(connector.connector_id) ?? []
  }));
}

export function permissionSetDifference(
  persisted: GroupPermissionSet,
  draft: GroupPermissionSet
): UpdateGroupPermissionsRequest {
  const persistedConnectors = new Set(persisted.connectorIds);
  const draftConnectors = new Set(draft.connectorIds);
  const persistedCapabilities = new Set(persisted.capabilities.map(capabilityPermissionId));
  const draftCapabilities = new Set(draft.capabilities.map(capabilityPermissionId));
  const connectors = [...new Set([...persistedConnectors, ...draftConnectors])]
    .sort()
    .filter((connectorId) => persistedConnectors.has(connectorId) !== draftConnectors.has(connectorId))
    .map((connectorId) => ({
      connector_id: connectorId,
      permission_status: draftConnectors.has(connectorId) ? 'enabled' as const : 'disabled' as const
    }));
  const capabilities = [...new Set([...persistedCapabilities, ...draftCapabilities])]
    .sort()
    .filter((capabilityId) => persistedCapabilities.has(capabilityId) !== draftCapabilities.has(capabilityId))
    .map((capabilityId) => {
      const [connectorId, capabilityKind, capabilityKey] = capabilityId.split('\u0000') as [
        string,
        CapabilityKind,
        string
      ];
      return {
        connector_id: connectorId,
        capability_kind: capabilityKind,
        capability_key: capabilityKey,
        permission_status: draftCapabilities.has(capabilityId) ? 'enabled' as const : 'disabled' as const
      };
    });
  return { connectors, capabilities };
}
