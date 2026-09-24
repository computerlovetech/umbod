import { HttpError, type Transport } from './infrastructure/transport';
import {
  apiAssignableTargetsResponseSchema,
  apiGroupPermissionSetSchema,
  apiGroupPermissionsResponseSchema,
  exactMatchGuidance,
  mapAssignableTargets,
  mapGroupPermissionSet,
  mapGroupPermissionSummary,
  updateGroupPermissionsRequestSchema,
  updateGroupPermissionsResponseSchema,
  type GroupPermissionSet,
  type GroupPermissionsActionResult,
  type GroupPermissionsPageData,
  type SaveGroupPermissionsResult,
  type UpdateGroupPermissionsRequest
} from './group-permissions';

const groupsPath = '/admin/mcp-permissions/groups';
const assignableTargetsPath = '/admin/mcp-permissions/assignable-targets';

function groupPath(groupId: string): string {
  return `${groupsPath}/${encodeURIComponent(groupId)}`;
}

export class GroupPermissionsRoute {
  constructor(private readonly transport: Transport) {}

  async list() {
    const response = await this.transport.request({ method: 'GET', path: groupsPath, outputSchema: apiGroupPermissionsResponseSchema });
    return response.groups.map(mapGroupPermissionSummary);
  }

  async get(groupId: string): Promise<GroupPermissionSet> {
    const response = await this.transport.request({ method: 'GET', path: groupPath(groupId), outputSchema: apiGroupPermissionSetSchema });
    return mapGroupPermissionSet(response);
  }

  async listAssignableTargets() {
    const response = await this.transport.request({ method: 'GET', path: assignableTargetsPath, outputSchema: apiAssignableTargetsResponseSchema });
    return mapAssignableTargets(response);
  }

  register(groupId: string): Promise<void> {
    return this.transport.request({ method: 'POST', path: groupPath(groupId) });
  }

  delete(groupId: string): Promise<void> {
    return this.transport.request({ method: 'DELETE', path: groupPath(groupId) });
  }

  update(groupId: string, payload: UpdateGroupPermissionsRequest) {
    return this.transport.request({
      method: 'PUT',
      path: `${groupPath(groupId)}/permissions`,
      body: payload,
      inputSchema: updateGroupPermissionsRequestSchema,
      outputSchema: updateGroupPermissionsResponseSchema
    });
  }
}

export class GroupPermissionsApi {
  readonly permissions: GroupPermissionsRoute;

  constructor(transport: Transport) {
    this.permissions = new GroupPermissionsRoute(transport);
  }
}

export async function loadGroupPermissions(api: GroupPermissionsApi): Promise<GroupPermissionsPageData> {
  const groups = await api.permissions.list();
  const selectedGroup = groups[0];

  if (selectedGroup === undefined) {
    return {
      status: 'ready',
      groups,
      preloadedGroup: null,
      assignableTargets: [],
      exactMatchGuidance,
      initialTarget: null,
      originHref: null
    };
  }

  const [preloadedGroup, assignableTargets] = await Promise.all([
    api.permissions.get(selectedGroup.groupId),
    api.permissions.listAssignableTargets()
  ]);

  return {
    status: 'ready',
    groups,
    preloadedGroup,
    assignableTargets,
    exactMatchGuidance,
    initialTarget: null,
    originHref: null
  };
}

export async function registerPermissionGroup(api: GroupPermissionsApi, groupId: string): Promise<GroupPermissionsActionResult> {
  try {
    await api.permissions.register(groupId);
    return { status: 'registered', groupId };
  } catch (error) {
    return rejectableActionResult(error, groupId, [400, 409], 'Permission group could not be registered');
  }
}

export async function deletePermissionGroup(api: GroupPermissionsApi, groupId: string): Promise<GroupPermissionsActionResult> {
  try {
    await api.permissions.delete(groupId);
    return { status: 'deleted', groupId };
  } catch (error) {
    return rejectableActionResult(error, groupId, [400, 409], 'Permission group could not be deleted');
  }
}

export async function updateGroupPermissions(
  api: GroupPermissionsApi,
  groupId: string,
  changes: UpdateGroupPermissionsRequest
): Promise<SaveGroupPermissionsResult> {
  try {
    await api.permissions.update(groupId, changes);
    return { status: 'saved', groupId };
  } catch (error) {
    return rejectableActionResult(error, groupId, [400, 404, 422], 'Permissions could not be saved');
  }
}

function rejectableActionResult(
  error: unknown,
  groupId: string,
  rejectStatuses: number[],
  fallback: string
): GroupPermissionsActionResult {
  if (error instanceof HttpError) {
    const message = permissionChangeErrorMessage(error, fallback);
    return rejectStatuses.includes(error.status) ? { status: 'rejected', groupId, message } : { status: 'failed', groupId, message };
  }
  throw error;
}

function permissionChangeErrorMessage(error: HttpError, fallback: string): string {
  const body = error.body as { message?: string; detail?: string } | null;
  return body?.message ?? body?.detail ?? fallback;
}
