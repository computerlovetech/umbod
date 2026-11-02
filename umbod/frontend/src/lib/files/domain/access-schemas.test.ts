import { describe, expect, test } from 'vitest';
import { nodeSummarySchema, type NodeSummary } from './schemas';
import { fileId, filesystemNode } from '../fixtures.test-support';

const owner = { type: 'user', issuer: 'https://identity.test', id: 'owner' } as const;
const available = {
  type: 'available',
  scope: 'direct_node_policy',
  owner,
  grants: [],
  group_members_expanded: false
} satisfies NodeSummary['visible_to'];
const grant = {
  node_id: fileId,
  principal: { type: 'group', issuer: 'https://foreign.test', id: 'editors' },
  permissions: ['discover', 'read', 'write', 'delete', 'share'],
  recursive: true
};

function accepts(override: Record<string, unknown>): boolean {
  return nodeSummarySchema.safeParse({ ...filesystemNode(), ...override }).success;
}

describe('filesystem access wire metadata', () => {
  test.each(['restricted', 'unavailable'] as const)('accepts %s without inventing policy details', (type): void => {
    const node = filesystemNode({ visible_to: { type } });
    expect(nodeSummarySchema.parse(node).visible_to).toEqual({ type });
  });

  test('accepts an available owner policy with no actual grants', (): void => {
    const node = filesystemNode({ visible_to: available });
    expect(nodeSummarySchema.parse(node).visible_to).toEqual(available);
  });

  test.each(['user', 'group', 'system'] as const)('accepts %s owners and foreign group grants without expanding members', (type): void => {
    const visible_to = { ...available, owner: { ...owner, type }, grants: [grant] };
    expect(nodeSummarySchema.parse({ ...filesystemNode(), visible_to }).visible_to).toEqual(visible_to);
  });

  test('preserves explicit denied permissions', (): void => {
    const permissions = { can_discover: true, can_read: false, can_write: false, can_delete: false, can_share: false };
    expect(nodeSummarySchema.parse({ ...filesystemNode(), permissions }).permissions).toEqual(permissions);
  });

  test.each(['permissions', 'visible_to'] as const)('requires %s on every summary', (field): void => {
    const node: Record<string, unknown> = { ...filesystemNode() };
    delete node[field];
    expect(nodeSummarySchema.safeParse(node).success).toBe(false);
    expect(accepts({ [field]: null })).toBe(false);
  });

  test.each(['can_discover', 'can_read', 'can_write', 'can_delete', 'can_share'] as const)('requires boolean %s', (flag): void => {
    for (const invalid of [undefined, null, 'true', 1, {}]) {
      expect(accepts({ permissions: { ...filesystemNode().permissions, [flag]: invalid } })).toBe(false);
    }
  });

  test.each([
    {},
    { type: 'unknown' },
    { type: 'restricted', owner },
    { type: 'unavailable', grants: [] },
    { ...available, scope: 'inherited' },
    { ...available, group_members_expanded: true },
    { ...available, group_members_expanded: undefined },
    { ...available, owner: undefined },
    { ...available, grants: undefined },
    { ...available, members: [] }
  ])('rejects malformed visibility %j', (visible_to): void => {
    expect(accepts({ visible_to })).toBe(false);
  });

  test.each([
    null,
    { ...owner, type: 'service' },
    { ...owner, issuer: 1 },
    { ...owner, issuer: undefined },
    { ...owner, id: null },
    { ...owner, id: undefined },
    { ...owner, display_name: 'Private' }
  ])('rejects malformed owners and grant principals %j', (principal): void => {
    expect(accepts({ visible_to: { ...available, owner: principal } })).toBe(false);
    expect(accepts({ visible_to: { ...available, grants: [{ ...grant, principal }] } })).toBe(false);
  });

  test.each([
    null,
    { ...grant, node_id: 'invalid' },
    { ...grant, permissions: ['admin'] },
    { ...grant, permissions: 'read' },
    { ...grant, permissions: undefined },
    { ...grant, recursive: 'true' },
    { ...grant, recursive: undefined },
    { ...grant, members: [] }
  ])('rejects malformed grants %j', (invalidGrant): void => {
    expect(accepts({ visible_to: { ...available, grants: [invalidGrant] } })).toBe(false);
  });

  test('keeps summary and permissions objects strict', (): void => {
    expect(accepts({ extra: true })).toBe(false);
    expect(accepts({ permissions: { ...filesystemNode().permissions, extra: true } })).toBe(false);
  });
});
