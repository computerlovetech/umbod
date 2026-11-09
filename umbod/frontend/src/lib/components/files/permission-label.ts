import type { NodeSummary } from '$lib/files/domain/schemas';

export function permissionLabel(permissions: NodeSummary['permissions']): string {
  const { can_discover, can_read, can_write, can_delete, can_share } = permissions;
  if (can_read && can_write) return 'Can edit';
  if (can_read && !can_write && !can_delete && !can_share) return 'Read only';
  if (can_discover && !can_read && !can_write && !can_delete && !can_share) return 'Details only';
  return 'Custom access';
}
