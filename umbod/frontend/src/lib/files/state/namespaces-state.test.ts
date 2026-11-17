import { afterEach, describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, HttpError } from '#lib/admin/infrastructure/transport.js';
import { resolveWorkspaceAccess } from '#lib/workspace/admin-access.js';
import { InMemoryWorkspaceApi } from '#lib/workspace/in-memory-api.test-support.js';
import { FilesState } from './files-state.svelte';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { deferred, filesystemNode, rootId, folderId, fileId } from '../fixtures.test-support';
import type { Breadcrumbs, FilesystemNamespace, BrowseResult } from '../domain/schemas';

afterEach((): void => { vi.restoreAllMocks(); });

const namespaces: FilesystemNamespace[] = [
  { id: rootId, root_node_id: rootId, name: 'Private storage', description: '', kind: 'personal', permissions: ['discover', 'read', 'write', 'delete'] },
  { id: folderId, root_node_id: folderId, name: 'Research', description: 'Shared research', kind: 'shared', permissions: ['discover', 'read'] }
];

function fixture(): { api: InMemoryFilesApi; state: FilesState } {
  const api = new InMemoryFilesApi(rootId, [
    filesystemNode(),
    filesystemNode({ id: folderId, parent_id: rootId, name: 'Research' }),
    filesystemNode({ id: fileId, parent_id: folderId, name: 'Report.txt', kind: 'file' })
  ]);
  vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue(namespaces);
  return { api, state: new FilesState(api) };
}

describe('personal and shared namespaces', () => {
  test('defaults to personal files and preserves explicit shared node links with namespace-relative paths', async (): Promise<void> => {
    const { api, state } = fixture();
    const browse = vi.spyOn(api.filesystem, 'browse');
    await state.load(null);
    expect(state.node?.id).toBe(rootId);
    expect(state.locationName).toBe('My files');
    expect(state.namespaces.map((entry) => entry.kind)).toEqual(['personal', 'shared']);
    await state.load(folderId);
    expect(browse).toHaveBeenLastCalledWith(folderId, expect.any(AbortSignal));
    expect(state.selectedNamespace?.id).toBe(folderId);
    expect(state.locationName).toBe('Research');
    expect(state.navigation.displayItems.map((item) => item.id)).toEqual([folderId]);
    await state.load(fileId);
    expect(state.selectedNamespace?.id).toBe(folderId);
    expect(state.navigation.displayItems.map((item) => item.id)).toEqual([folderId, fileId]);
    expect(state.navigation.label(state.navigation.parent!)).toBe('Research');
    expect(state.navigation.href(state.navigation.parent!)).toBe('/files?node=' + folderId);
    state.dispose();
  });

  test.each([
    [fileId, 'empty'], [folderId, 'empty'],
    [fileId, 'denied'], [folderId, 'denied']
  ] as const)('opens shared item %s directly with %s namespace inventory', async (target, inventory): Promise<void> => {
    const nodes = [
      filesystemNode(),
      filesystemNode({ id: folderId, parent_id: rootId, name: 'Shared folder' }),
      filesystemNode({ id: fileId, parent_id: folderId, name: 'Shared file.txt', kind: 'file' })
    ];
    const api = new InMemoryFilesApi(rootId, nodes, undefined, undefined, (node) => node.id !== rootId, () => false);
    const catalogue = vi.spyOn(api.filesystem, 'listNamespaces');
    if (inventory === 'empty') catalogue.mockResolvedValue([]);
    else catalogue.mockRejectedValue(new HttpError(403, 'Forbidden', {}));
    const state = new FilesState(api);
    try {
      await state.load(target);
      expect(state.phase).toBe('ready');
      expect(state.node?.id).toBe(target);
      expect(state.namespaces).toEqual([]);
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.navigation.displayItems.map((item) => item.id)).not.toContain(rootId);
      expect(state.navigation.displayComplete).toBe(false);
      expect(state.locationName).toBe(target === fileId ? 'Shared file.txt' : 'Shared folder');
      expect(state.sharing.available(target)).toBe(false);
      expect(state.children.map((node) => node.id)).toEqual(target === folderId ? [fileId] : []);
    } finally {
      state.dispose();
    }
  });

  test('projects ordered groups, personal labels, native hrefs and deepest selected namespace', async (): Promise<void> => {
    const { state } = fixture();
    try {
      await state.load(fileId);
      expect(state.locationGroups).toEqual([
        { kind: 'personal', label: 'Personal', locations: [{ id: rootId, label: 'My files', href: '/files?node=' + rootId, selected: false }] },
        { kind: 'shared', label: 'Shared namespaces', locations: [{ id: folderId, label: 'Research', href: '/files?node=' + folderId, selected: true }] }
      ]);
    } finally { state.dispose(); }
  });

  test('grouping preserves backend ordering within each kind', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([namespaces[1], namespaces[0], { ...namespaces[1], id: fileId, root_node_id: fileId, name: 'Another shared namespace' }]);
      await state.load(null);
      expect(state.locationGroups.map((group) => group.kind)).toEqual(['personal', 'shared']);
      expect(state.locationGroups[1].locations.map((location) => location.id)).toEqual([folderId, fileId]);
    } finally { state.dispose(); }
  });

  test('revoked personal root stops default browsing without falling back to a shared root', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(null);
      vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([namespaces[1]]);
      const browse = vi.spyOn(api.filesystem, 'browse');
      await state.reload();
      expect(browse).not.toHaveBeenCalled();
      expect(state.discoveryPhase).toBe('ready');
      expect(state.phase).toBe('error');
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.locationGroups.map((group) => group.kind)).toEqual(['shared']);
      expect(state.creationTarget()).toBeUndefined();
    } finally { state.dispose(); }
  });

  test('disposed loads cannot restore retained inventory from late discovery', async (): Promise<void> => {
    const { api, state } = fixture();
    await state.load(folderId);
    const pending = deferred<FilesystemNamespace[]>();
    vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(pending.promise);
    const loading = state.reload();
    state.dispose();
    pending.resolve(namespaces);
    await loading;
    expect(state.namespaces).toEqual([]);
    expect(state.selectedNamespace).toBeUndefined();
  });

  test('retains confirmed inventory and shared context while nested navigation discovers and browses', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(folderId);
      const result = await api.filesystem.browse(fileId);
      const inventory = deferred<FilesystemNamespace[]>();
      const browsing = deferred<BrowseResult>();
      vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(inventory.promise);
      vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(browsing.promise);
      const loading = state.load(fileId);
      expect(state.namespaces).toEqual(namespaces);
      expect(state.selectedNamespace?.id).toBe(folderId);
      expect(state.discoveryPhase).toBe('loading');
      expect(state.node?.id).toBe(folderId);
      expect(state.creationTarget()).toBeUndefined();
      inventory.resolve(namespaces);
      await vi.waitFor((): void => expect(state.discoveryPhase).toBe('ready'));
      expect(state.selectedNamespace?.id).toBe(folderId);
      expect(state.phase).toBe('loading');
      browsing.resolve(result);
      await loading;
      expect(state.selectedNamespace?.id).toBe(folderId);
      expect(state.phase).toBe('ready');
    } finally { state.dispose(); }
  });

  test('known roots retain confirmed selection until commit and independent path reload preserves context', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(folderId);
      const inventory = deferred<FilesystemNamespace[]>();
      vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(inventory.promise);
      const loading = state.load(null);
      expect(state.selectedNamespace?.id).toBe(folderId);
      inventory.resolve(namespaces);
      await loading;
      await state.load(fileId);
      const path = await api.filesystem.getBreadcrumbs(fileId);
      const pending = deferred<Breadcrumbs>();
      vi.spyOn(api.filesystem, 'getBreadcrumbs').mockReturnValueOnce(pending.promise);
      const reloading = state.navigation.reload();
      expect(state.navigation.displayItems).toEqual([]);
      expect(state.selectedNamespace?.id).toBe(folderId);
      pending.resolve(path);
      await reloading;
      expect(state.selectedNamespace?.id).toBe(folderId);
    } finally { state.dispose(); }
  });

  test.each([true, false])('partial ancestry only selects a disclosed known namespace: %s', async (known): Promise<void> => {
    const { api, state } = fixture();
    try {
      const result = await api.filesystem.browse(fileId);
      vi.spyOn(api.filesystem, 'browse').mockResolvedValue({
        ...result,
        node: { ...result.node, visible_to: { type: 'namespace', namespace_id: known ? folderId : fileId, kind: 'shared', name: 'Never create a link' } },
        breadcrumbs: { items: result.breadcrumbs.items.slice(-1), complete: false }
      });
      await state.load(fileId);
      expect(state.selectedNamespace?.id).toBe(known ? folderId : undefined);
      expect(state.namespaces).toEqual(namespaces);
      expect(state.locationGroups.flatMap((group) => group.locations).map((location) => location.label)).not.toContain('Never create a link');
    } finally { state.dispose(); }
  });

  test.each([
    ['empty', undefined, 'ready'],
    ['denied', new HttpError(403, 'Forbidden', {}), 'denied'],
    ['error', new Error('Private diagnostic'), 'error'],
    ['sign-in', new AuthenticationRequiredError(), 'sign-in']
  ] as const)('explicit UUID browsing survives %s discovery without fabricated links', async (_name, error, phase): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(null);
      if (error) vi.mocked(api.filesystem.listNamespaces).mockRejectedValueOnce(error);
      else vi.mocked(api.filesystem.listNamespaces).mockResolvedValueOnce([]);
      await state.load(fileId);
      expect(state.phase).toBe('ready');
      expect(state.discoveryPhase).toBe(phase);
      expect(state.locationGroups).toEqual([]);
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.node?.id).toBe(fileId);
    } finally { state.dispose(); }
  });

  test('failed default discovery cannot browse the retained personal root', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(null);
      const browse = vi.spyOn(api.filesystem, 'browse');
      vi.mocked(api.filesystem.listNamespaces).mockRejectedValueOnce(new Error('Private diagnostic'));
      await state.reload();
      expect(browse).not.toHaveBeenCalled();
      expect(state.phase).toBe('error');
      expect(state.locationGroups).toEqual([]);
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.creationTarget()).toBeUndefined();
      expect(state.uploadAvailability).toBe('hidden');
    } finally { state.dispose(); }
  });

  test('refresh removes revoked roots and resolved unrelated targets clear the old highlight', async (): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(fileId);
      vi.mocked(api.filesystem.listNamespaces).mockResolvedValueOnce([namespaces[0]]);
      await state.reload();
      expect(state.namespaces).toEqual([namespaces[0]]);
      expect(state.selectedNamespace?.id).toBe(rootId);
      vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([namespaces[1]]);
      await state.load(folderId);
      await state.load(rootId);
      expect(state.phase).toBe('ready');
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.locationGroups[0].locations[0].selected).toBe(false);
    } finally { state.dispose(); }
  });

  test.each([new Error('Private diagnostic'), new HttpError(404, 'Missing', {}), new HttpError(403, 'Denied', {})])('browse failure clears selection and action eligibility without redirecting', async (error): Promise<void> => {
    const { api, state } = fixture();
    try {
      await state.load(folderId);
      const browse = vi.spyOn(api.filesystem, 'browse').mockRejectedValueOnce(error);
      await state.load(fileId);
      expect(browse).toHaveBeenCalledTimes(1);
      expect(browse).toHaveBeenCalledWith(fileId, expect.any(AbortSignal));
      expect(state.selectedNamespace).toBeUndefined();
      expect(state.node).toBeUndefined();
      expect(state.creationTarget()).toBeUndefined();
      expect(state.uploadAvailability).toBe('hidden');
      expect(state.createDirectoryAllowed).toBe(false);
    } finally { state.dispose(); }
  });

  test('invalid UUID ends discovery loading and clears selected context', async (): Promise<void> => {
    const { state } = fixture();
    try {
      await state.load(folderId);
      await state.load('not-a-uuid');
      expect(state.discoveryPhase).toBe('error');
      expect(state.phase).toBe('error');
      expect(state.selectedNamespace).toBeUndefined();
    } finally { state.dispose(); }
  });

  test('hidden identity immediately clears retained inventory and disposal fences late discovery', async (): Promise<void> => {
    const { api, state } = fixture();
    state.observeAccountIdentity({ kind: 'visible', name: 'User', email: null, picture: null, hiddenValues: { id: 'opaque-key' } });
    await state.load(folderId);
    const pending = deferred<FilesystemNamespace[]>();
    vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(pending.promise);
    state.observeAccountIdentity({ kind: 'hidden' });
    expect(state.namespaces).toEqual([]);
    expect(state.selectedNamespace).toBeUndefined();
    expect(state.node).toBeUndefined();
    state.dispose();
    pending.resolve(namespaces);
    await Promise.resolve();
    await Promise.resolve();
    expect(state.namespaces).toEqual([]);
    expect(state.selectedNamespace).toBeUndefined();
  });

  test('late namespace listings cannot replace a newer selection', async (): Promise<void> => {
    const { api, state } = fixture();
    const pending = deferred<FilesystemNamespace[]>();
    vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(pending.promise);
    const first = state.load(null);
    await state.load(folderId);
    pending.resolve([namespaces[0]]);
    await first;
    expect(state.selectedNamespace?.id).toBe(folderId);
    expect(state.namespaces).toHaveLength(2);
    state.dispose();
  });

  test.each(['rejected', 'invalid'] as const)('obsolete %s discovery cannot clear a newer successful selection', async (outcome): Promise<void> => {
    const { api, state } = fixture();
    try {
      const pending = deferred<FilesystemNamespace[]>();
      vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(pending.promise);
      const first = state.load(null);
      await state.load(folderId);
      const inventory = state.namespaces;
      if (outcome === 'rejected') pending.reject(new HttpError(403, 'Obsolete denial', {}));
      else pending.resolve([{ ...namespaces[0], root_node_id: 'invalid-uuid' }]);
      await first;
      expect(state.namespaces).toBe(inventory);
      expect(state.selectedNamespace?.id).toBe(folderId);
      expect(state.discoveryPhase).toBe('ready');
      expect(state.phase).toBe('ready');
      expect(state.node?.id).toBe(folderId);
    } finally { state.dispose(); }
  });

  test.each(['rejected', 'invalid'] as const)('obsolete %s discovery cannot clear a new identity inventory', async (outcome): Promise<void> => {
    const { api, state } = fixture();
    try {
      state.observeAccountIdentity({ kind: 'visible', name: 'User', email: null, picture: null, hiddenValues: { id: 'opaque-issuer-a' } });
      const pending = deferred<FilesystemNamespace[]>();
      vi.mocked(api.filesystem.listNamespaces).mockReturnValueOnce(pending.promise);
      const first = state.load(folderId);
      vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([namespaces[1]]);
      state.observeAccountIdentity({ kind: 'visible', name: 'User', email: null, picture: null, hiddenValues: { id: 'opaque-issuer-b' } });
      await vi.waitFor((): void => expect(state.phase).toBe('ready'));
      const inventory = state.namespaces;
      if (outcome === 'rejected') pending.reject(new Error('Obsolete failure'));
      else pending.resolve([{ ...namespaces[0], root_node_id: 'invalid-uuid' }]);
      await first;
      expect(state.namespaces).toBe(inventory);
      expect(state.namespaces).toEqual([namespaces[1]]);
      expect(state.selectedNamespace?.id).toBe(folderId);
      expect(state.discoveryPhase).toBe('ready');
      expect(state.phase).toBe('ready');
      expect(state.node?.id).toBe(folderId);
    } finally { state.dispose(); }
  });

  test('identity changes fence pending browse results and clear namespace inventories immediately', async (): Promise<void> => {
    const { api, state } = fixture();
    const user = { id: 'same-raw-subject', name: 'Same display name', email: null, picture: null };
    const profileA = { identity_key: 'opaque-key-7ec4', user, capabilities: { administration: false } };
    const profileB = { identity_key: 'opaque-key-91bd', user, capabilities: { administration: false } };
    const accountA = await resolveWorkspaceAccess(new InMemoryWorkspaceApi(profileA));
    const accountB = await resolveWorkspaceAccess(new InMemoryWorkspaceApi(profileB));
    expect(profileA.user.id).toBe(profileB.user.id);
    expect(accountA.accountIdentity).toMatchObject({ hiddenValues: { id: profileA.identity_key } });
    expect(accountB.accountIdentity).toMatchObject({ hiddenValues: { id: profileB.identity_key } });
    state.observeAccountIdentity(accountA.accountIdentity);
    const result = await api.filesystem.browse(folderId);
    const pending = deferred<BrowseResult>();
    vi.spyOn(api.filesystem, 'browse').mockReturnValueOnce(pending.promise);
    const first = state.load(folderId);
    await vi.waitFor(() => expect(api.filesystem.browse).toHaveBeenCalledTimes(1));
    vi.mocked(api.filesystem.listNamespaces).mockResolvedValue([namespaces[0]]);
    state.observeAccountIdentity(accountB.accountIdentity);
    expect(state.node).toBeUndefined();
    expect(state.namespaces).toEqual([]);
    await vi.waitFor(() => expect(state.phase).toBe('ready'));
    pending.resolve(result);
    await first;
    expect(state.namespaces).toEqual([namespaces[0]]);
    state.dispose();
  });
});
