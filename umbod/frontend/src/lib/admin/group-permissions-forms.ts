import { updateGroupPermissionsRequestSchema, type UpdateGroupPermissionsRequest } from './group-permissions';

export function parseGroupIdFormValue(value: FormDataEntryValue | null): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

export function parsePermissionSetFormValue(value: FormDataEntryValue | null, groupId: string): UpdateGroupPermissionsRequest {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error(`Permission changes are required for ${groupId}`);
  }

  return updateGroupPermissionsRequestSchema.parse(JSON.parse(value));
}
