import { InMemoryNamespaceAdministration } from '../../../../../tests/support/filesystem/in-memory-namespace-administration';
import type { NamespaceAdministration } from '$lib/admin/filesystem/namespaces-port';
import { vi, type Mock, type MockInstance } from 'vitest';
import type { CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import type { GroupPermissionSet } from '$lib/admin/group-permissions';
import { InMemoryGroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionsSaver } from './group-permissions-saver';
import { GroupPermissionsWorkspaceState } from './group-permissions-workspace-state.svelte';

interface WorkspaceFixture {
  state: GroupPermissionsWorkspaceState;
  catalogue: CatalogueGroup[];
  loader: InMemoryGroupPermissionsLoader;
  detail: MockInstance<InMemoryGroupPermissionsLoader['loadGroup']>;
  targets: MockInstance<InMemoryGroupPermissionsLoader['loadAssignableTargets']>;
  save: Mock<(groupId: string) => Promise<GroupPermissionSet>>;
}

export const createWorkspace = (saver?: GroupPermissionsSaver, namespaces: NamespaceAdministration = new InMemoryNamespaceAdministration([], ['a', 'b'])): WorkspaceFixture => {
  const catalogue: CatalogueGroup[] = ['a', 'b'].map((group_id) => ({ group_id, label: group_id === 'a' ? 'Operators' : 'Readers', description: '', revision: 1 }));
  const loader = new InMemoryGroupPermissionsLoader(new Map(catalogue.map((group) => [group.group_id, { groupId: group.group_id, connectorIds: [], capabilities: [] }])), [{ id: 'reports', displayName: 'Reports', description: '', capabilities: [] }]);
  const save = vi.fn(async (groupId: string): Promise<GroupPermissionSet> => ({ groupId, connectorIds: ['reports'], capabilities: [] }));
  const detail = vi.spyOn(loader, 'loadGroup');
  const targets = vi.spyOn(loader, 'loadAssignableTargets');
  const state = new GroupPermissionsWorkspaceState(() => catalogue, loader, saver ?? { save }, () => null, namespaces);
  return { state, catalogue, loader, detail, targets, save };
};
