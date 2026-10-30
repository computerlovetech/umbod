import { vi, type Mock, type MockInstance } from 'vitest';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';
import type { CatalogueGroup } from '$lib/admin/groups/domain/schemas';
import type { GroupPermissionSet } from '$lib/admin/group-permissions';
import { InMemoryGroupPermissionsLoader } from './group-permissions-loader';
import type { GroupPermissionsSaver } from './group-permissions-saver';
import { GroupPermissionsWorkspaceState } from './group-permissions-workspace-state.svelte';

interface WorkspaceFixture {
  state: GroupPermissionsWorkspaceState;
  catalogue: CatalogueGroup[];
  groups: InMemoryGroupCatalogue;
  filesystem: InMemoryFilesystemAdministration;
  loader: InMemoryGroupPermissionsLoader;
  list: MockInstance<InMemoryGroupCatalogue['list']>;
  root: MockInstance<InMemoryFilesystemAdministration['getRootAccess']>;
  detail: MockInstance<InMemoryGroupPermissionsLoader['loadGroup']>;
  targets: MockInstance<InMemoryGroupPermissionsLoader['loadAssignableTargets']>;
  save: Mock<(groupId: string) => Promise<GroupPermissionSet>>;
}

export const createWorkspace = (saver?: GroupPermissionsSaver): WorkspaceFixture => {
  const catalogue: CatalogueGroup[] = ['a', 'b'].map((group_id) => ({ group_id, label: group_id === 'a' ? 'Operators' : 'Readers', description: '', revision: 1 }));
  const groups = new InMemoryGroupCatalogue(catalogue);
  const filesystem = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ group_id: 'orphan', permissions: ['read'] }] }));
  const loader = new InMemoryGroupPermissionsLoader(new Map(catalogue.map((group) => [group.group_id, { groupId: group.group_id, connectorIds: [], capabilities: [] }])), [{ id: 'reports', displayName: 'Reports', description: '', capabilities: [] }]);
  const save = vi.fn(async (groupId: string): Promise<GroupPermissionSet> => ({ groupId, connectorIds: ['reports'], capabilities: [] }));
  const list = vi.spyOn(groups, 'list');
  const root = vi.spyOn(filesystem, 'getRootAccess');
  const detail = vi.spyOn(loader, 'loadGroup');
  const targets = vi.spyOn(loader, 'loadAssignableTargets');
  const state = new GroupPermissionsWorkspaceState(() => catalogue, groups, filesystem, loader, saver ?? { save }, () => null);
  return { state, catalogue, groups, filesystem, loader, list, root, detail, targets, save };
};
