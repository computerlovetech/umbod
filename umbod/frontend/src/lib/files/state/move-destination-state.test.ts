import { afterEach, describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '../fixtures.test-support';
import type { NodeSummary } from '../domain/schemas';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import { MoveDestinationState, type DestinationFolder } from './move-destination-state.svelte';

const states: MoveDestinationState[] = [];

afterEach((): void => {
  for (const state of states) state.reset();
  states.length = 0;
  vi.restoreAllMocks();
});

function picker(api: InMemoryFilesApi, personalRoot: string = rootId, locked: () => boolean = () => false): MoveDestinationState {
  const state = new MoveDestinationState(api.filesystem, () => personalRoot, locked);
  states.push(state);
  return state;
}

function folder(state: MoveDestinationState, id: string): DestinationFolder {
  function find(items: readonly DestinationFolder[]): DestinationFolder | undefined {
    for (const item of items) {
      if (item.id === id) return item;
      const child = find(item.children);
      if (child) return child;
    }
    return undefined;
  }
  const found = find(state.folders);
  expect(found).toBeDefined();
  return found!;
}

async function createFolder(api: InMemoryFilesApi, parentId: string, name: string): Promise<NodeSummary> {
  return api.filesystem.createFolder(parentId, { name, metadata: { content_type: {}, attributes: {} } });
}

describe('move destination picker', (): void => {
  test('opens the path to the current folder without selecting a destination or listing files', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    expect(state.folders).toMatchObject([{ id: rootId, name: 'Home', expanded: true, children: [{ id: folderId, name: 'Projects', current: true, selectable: false, expandable: false }] }]);
    expect(state.selected).toBeUndefined();
    expect(state.canSubmit).toBe(false);
    await state.select(folderId);
    await state.select(fileId);
    expect(state.selected).toBeUndefined();
  });

  test('expands and collapses independently of explicit selection and retains cached children', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const child = await createFolder(api, sibling.id, '2026');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    await state.select(rootId);
    const list = vi.spyOn(api.filesystem, 'listChildren');
    await state.toggle(sibling.id);
    expect(folder(state, child.id).selected).toBe(false);
    expect(state.selected?.id).toBe(rootId);
    await state.toggle(sibling.id);
    await state.toggle(sibling.id);
    expect(list).toHaveBeenCalledTimes(1);
    await state.select(child.id);
    expect(folder(state, child.id).selected).toBe(true);
    expect(state.selectedName).toBe('2026');
    expect(state.canSubmit).toBe(true);
    await state.toggle(sibling.id);
    expect(state.selected).toBeUndefined();
    expect(state.canSubmit).toBe(false);
  });

  test('loads independent branches concurrently without cancelling either response', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const first = await createFolder(api, rootId, 'First');
    const second = await createFolder(api, rootId, 'Second');
    const firstChild = await createFolder(api, first.id, 'First child');
    const secondChild = await createFolder(api, second.id, 'Second child');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    const firstResponse = deferred<NodeSummary[]>();
    const secondResponse = deferred<NodeSummary[]>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(firstResponse.promise).mockReturnValueOnce(secondResponse.promise);
    const loadingFirst = state.toggle(first.id);
    const loadingSecond = state.toggle(second.id);
    expect(folder(state, first.id).phase).toBe('loading');
    expect(folder(state, second.id).phase).toBe('loading');
    secondResponse.resolve([secondChild]);
    await loadingSecond;
    firstResponse.resolve([firstChild]);
    await loadingFirst;
    expect(folder(state, firstChild.id).name).toBe('First child');
    expect(folder(state, secondChild.id).name).toBe('Second child');
  });

  test('does not let an obsolete authorization replace the latest explicit selection', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    const response = deferred<void>();
    const check = vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValueOnce(response.promise);
    const first = state.select(rootId);
    await vi.waitFor(() => expect(check).toHaveBeenCalledWith(rootId));
    expect(state.canSubmit).toBe(false);
    await state.select(sibling.id);
    response.reject(new HttpError(403, 'Denied', {}));
    await first;
    expect(state.selected?.id).toBe(sibling.id);
    expect(state.canSubmit).toBe(true);
    expect(state.error).toBe('');
  });

  test('cancels selection when collapsing its ancestor while the destination is still loading', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    const response = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'getNode').mockReturnValueOnce(response.promise);
    const selecting = state.select(sibling.id);
    await state.toggle(rootId);
    response.resolve(sibling);
    await selecting;
    expect(state.selected).toBeUndefined();
    expect(state.canSubmit).toBe(false);
    expect(state.selecting).toBe(false);
  });

  test('allows browsing a read-only folder to find writable descendants', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, (node) => node.name !== 'Read only');
    const readOnly = await createFolder(api, rootId, 'Read only');
    const child = await createFolder(api, readOnly.id, 'Writable');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    expect(folder(state, readOnly.id).selectable).toBe(false);
    await state.select(readOnly.id);
    expect(state.selected).toBeUndefined();
    await state.toggle(readOnly.id);
    await state.select(child.id);
    expect(state.canSubmit).toBe(true);
  });

  test('retries a failed branch without losing selection in another branch', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    await state.select(rootId);
    const list = vi.spyOn(api.filesystem, 'listChildren').mockRejectedValueOnce(new Error('Offline'));
    await state.toggle(sibling.id);
    expect(folder(state, sibling.id).phase).toBe('error');
    expect(state.selected?.id).toBe(rootId);
    expect(state.canSubmit).toBe(true);
    await state.retryBranch(sibling.id);
    expect(folder(state, sibling.id).phase).toBe('ready');
    expect(folder(state, sibling.id).expandable).toBe(false);
    expect(list).toHaveBeenCalledTimes(2);
  });

  test('retries initial path failure without selecting the current folder', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = picker(api);
    const source = await api.filesystem.getNode(fileId);
    vi.spyOn(api.filesystem, 'getBreadcrumbs').mockRejectedValueOnce(new Error('Offline'));
    await state.open(source);
    expect(state.canRetry).toBe(true);
    expect(state.folders).toEqual([]);
    await state.retry();
    expect(state.canRetry).toBe(false);
    expect(state.error).toBe('');
    expect(folder(state, folderId).current).toBe(true);
  });

  test.each([403, 404, 500])('rejects destination authorization failure %s', async (status): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new HttpError(status, 'Failed', {}));
    await state.select(rootId);
    expect(state.canSubmit).toBe(false);
    expect(folder(state, rootId).selectable).toBe(status === 500);
    if (status === 500) {
      expect(state.error).toBe('Could not check destination. Try again.');
      await state.select(rootId);
      expect(state.canSubmit).toBe(true);
    }
  });

  test('does not expose a directory source or any of its descendants as destinations', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const child = await createFolder(api, folderId, 'Child');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(folderId));
    expect(folder(state, rootId).children).toEqual([]);
    await state.select(folderId);
    await state.select(child.id);
    expect(state.canSubmit).toBe(false);
  });

  test('rejects a destination whose authoritative path now contains the source directory', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(folderId));
    await api.filesystem.updateNode(sibling.id, 1, { parent_id: folderId });
    await state.select(sibling.id);
    expect(state.selected).toBeUndefined();
    expect(state.canSubmit).toBe(false);
  });

  test('starts at the accessible path boundary without querying an inaccessible global root', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, (node) => node.id !== rootId);
    const get = vi.spyOn(api.filesystem, 'getNode');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    expect(state.folders).toMatchObject([{ id: folderId, name: 'Projects', current: true }]);
    expect(get.mock.calls.some(([id]) => id === rootId)).toBe(false);
  });

  test('fences pending initialization, branch loads and authorization after reset', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const sibling = await createFolder(api, rootId, 'Archive');
    const state = picker(api);
    await state.open(await api.filesystem.getNode(fileId));
    const children = deferred<NodeSummary[]>();
    const authorization = deferred<void>();
    vi.spyOn(api.filesystem, 'listChildren').mockReturnValueOnce(children.promise);
    const check = vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValueOnce(authorization.promise);
    const loading = state.toggle(sibling.id);
    const selecting = state.select(rootId);
    await vi.waitFor(() => expect(check).toHaveBeenCalled());
    state.reset();
    children.resolve([]);
    authorization.resolve();
    await Promise.all([loading, selecting]);
    expect(state.folders).toEqual([]);
    expect(state.selected).toBeUndefined();
    expect(state.canSubmit).toBe(false);
    const source = await api.filesystem.getNode(fileId);
    const parent = deferred<NodeSummary>();
    vi.spyOn(api.filesystem, 'getNode').mockReturnValueOnce(parent.promise);
    const opening = state.open(source);
    state.reset();
    parent.resolve(filesystemFixture[1]);
    await opening;
    expect(state.folders).toEqual([]);
    expect(state.loading).toBe(false);
  });

  test('prevents selection and expansion changes while the owning mutation is pending', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    let locked = false;
    const state = picker(api, rootId, () => locked);
    await state.open(await api.filesystem.getNode(fileId));
    await state.select(rootId);
    locked = true;
    await state.toggle(rootId);
    await state.select(folderId);
    expect(folder(state, rootId).expanded).toBe(true);
    expect(state.selected?.id).toBe(rootId);
  });
});
