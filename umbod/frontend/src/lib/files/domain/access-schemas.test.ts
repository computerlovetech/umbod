import { describe, expect, test } from 'vitest';
import { filesystemNamespaceSchema, nodeSummarySchema } from './schemas';
import { filesystemNode, rootId } from '../fixtures.test-support';

const namespace = { type: 'namespace', namespace_id: rootId, kind: 'shared', name: 'Design' } as const;

function accepts(override: Record<string, unknown>): boolean {
  return nodeSummarySchema.safeParse({ ...filesystemNode(), ...override }).success;
}

describe('filesystem access wire metadata', (): void => {
  test('accepts restricted visibility without inventing namespace details', (): void => {
    const node = filesystemNode({ visible_to: { type: 'restricted' } });
    expect(nodeSummarySchema.parse(node).visible_to).toEqual({ type: 'restricted' });
  });

  test.each(['personal', 'shared'] as const)('accepts %s namespace visibility', (kind): void => {
    const visible_to = { ...namespace, kind };
    expect(nodeSummarySchema.parse(filesystemNode({ visible_to })).visible_to).toEqual(visible_to);
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
    {}, { type: 'unknown' }, { type: 'unavailable' },
    { type: 'available', scope: 'direct_node_policy', owner: {}, grants: [] },
    { type: 'restricted', name: 'Private' },
    { ...namespace, namespace_id: 'invalid' },
    { ...namespace, namespace_id: undefined },
    { ...namespace, kind: 'group' },
    { ...namespace, name: undefined },
    { ...namespace, owner: {} },
    { ...namespace, grants: [] }
  ])('rejects malformed or retired visibility %j', (visible_to): void => {
    expect(accepts({ visible_to })).toBe(false);
  });

  test('rejects namespace sharing permissions and unexpected summary fields', (): void => {
    expect(accepts({ extra: true })).toBe(false);
    expect(accepts({ permissions: { ...filesystemNode().permissions, can_share: 'false' } })).toBe(false);
    expect(filesystemNamespaceSchema.safeParse({
      id: rootId, root_node_id: rootId, kind: 'personal', name: 'My files', description: '', permissions: ['share']
    }).success).toBe(false);
  });
});
