import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '../fixtures.test-support';
import { InMemoryFilesApi } from '../infrastructure/in-memory-api.test-support';
import type { NodeSummary } from '../domain/schemas';
import { FilesState } from './files-state.svelte';
import { fileMoveTransferType } from './drag-move-state.svelte';

const destinationId = '00000000-0000-4000-8000-000000000004';
const otherFileId = '00000000-0000-4000-8000-000000000005';
const states: FilesState[] = [];
type MutableTransfer = Omit<DataTransfer, 'types'> & { types: string[] };

beforeEach((): void => {
  vi.stubGlobal('Element', class {});
  vi.stubGlobal('Node', class {});
});

afterEach((): void => {
  for (const state of states.splice(0)) state.dispose();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function transfer(types: string[] = []): MutableTransfer {
  const data = new Map<string, string>();
  return {
    types,
    effectAllowed: 'uninitialized',
    dropEffect: 'none',
    clearData: (): void => { data.clear(); types.splice(0); },
    setData: (type: string, value: string): void => { data.set(type, value); if (!types.includes(type)) types.push(type); },
    getData: (type: string): string => data.get(type) ?? ''
  } as unknown as MutableTransfer;
}

function drag(dataTransfer: DataTransfer): DragEvent {
  return { dataTransfer, target: null, currentTarget: null, relatedTarget: null, preventDefault: vi.fn() } as unknown as DragEvent;
}

async function setup(deniedId?: string): Promise<{ api: InMemoryFilesApi; files: FilesState }> {
  const api = new InMemoryFilesApi(rootId, [...filesystemFixture,
    filesystemNode({ id: destinationId, parent_id: folderId, name: 'Archive' }),
    filesystemNode({ id: otherFileId, parent_id: folderId, name: 'Other.txt', kind: 'file' })
  ], undefined, undefined, undefined, (node): boolean => node.id !== deniedId);
  const files = new FilesState(api);
  states.push(files);
  await files.load(folderId);
  await vi.waitFor((): void => {
    expect(files.rowEditing.controllers.get(fileId)?.update.canMove).toBe(deniedId !== fileId && deniedId !== folderId);
    expect(files.rowEditing.controllers.get(destinationId)?.update.canRename).toBe(deniedId !== destinationId);
  });
  return { api, files };
}

function start(files: FilesState): MutableTransfer {
  const data = transfer();
  files.dragMove.start(fileId, drag(data));
  return data;
}

describe('file drag moves', (): void => {
  test('moves once with the authoritative revision and removes the row without reloading', async (): Promise<void> => {
    const { api, files } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const list = vi.spyOn(api.filesystem, 'listChildren');
    const data = start(files);
    expect(data.getData(fileMoveTransferType)).toBe(fileId);
    expect(data.effectAllowed).toBe('move');
    expect(files.dragMove.status).toBe('Drop “Notes.txt” onto a folder to move it.');
    files.dragMove.over(destinationId, drag(data));
    expect(files.dragMove.isTarget(destinationId)).toBe(true);
    expect(data.dropEffect).toBe('move');
    files.dragMove.drop(destinationId, drag(data));
    files.dragMove.drop(destinationId, drag(data));
    await vi.waitFor((): void => expect(files.dragMove.pending).toBe(false));
    expect(patch).toHaveBeenCalledExactlyOnceWith(fileId, 1, { parent_id: destinationId });
    expect(files.children.map((node): string => node.id)).toEqual([destinationId, otherFileId]);
    expect(list).not.toHaveBeenCalled();
    expect(files.dragMove.status).toBe('Moved “Notes.txt” to “Archive”.');
    expect(files.dragMove.isSource(fileId)).toBe(false);
    expect(files.dragMove.isTarget(destinationId)).toBe(false);
    await files.load(destinationId);
    expect(files.children).toMatchObject([{ id: fileId, parent_id: destinationId, revision: 2 }]);
  });

  test('clears highlighting on leave and cancellation without writing', async (): Promise<void> => {
    const { api, files } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const data = start(files);
    files.dragMove.over(destinationId, drag(data));
    files.dragMove.leave(destinationId, drag(data));
    expect(files.dragMove.isTarget(destinationId)).toBe(false);
    expect(files.dragMove.isSource(fileId)).toBe(true);
    files.dragMove.over(destinationId, drag(data));
    files.dragMove.cancel();
    expect(files.dragMove.status).toBe('');
    expect(files.dragMove.isSource(fileId)).toBe(false);
    expect(files.dragMove.isTarget(destinationId)).toBe(false);
    files.dragMove.drop(destinationId, drag(data));
    expect(patch).not.toHaveBeenCalled();
  });

  test.each([fileId, folderId])('requires update permission on source and parent %s', async (deniedId): Promise<void> => {
    const { api, files } = await setup(deniedId);
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const event = drag(transfer());
    expect(files.dragMove.canDrag(fileId)).toBe(false);
    files.dragMove.start(fileId, event);
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(files.dragMove.isSource(fileId)).toBe(false);
    expect(patch).not.toHaveBeenCalled();
  });

  test('waits for parent eligibility before allowing dragging', async (): Promise<void> => {
    const { api, files } = await setup();
    const gate = deferred<void>();
    const original = api.filesystem.checkUpdateEligibility;
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockImplementation((id, signal): Promise<void> => id === folderId ? gate.promise : original(id, signal));
    const checking = files.rowEditing.controllers.get(fileId)!.update.checkEligibility();
    await vi.waitFor((): void => expect(files.rowEditing.controllers.get(fileId)!.update.canRename).toBe(true));
    expect(files.dragMove.canDrag(fileId)).toBe(false);
    gate.resolve();
    await checking;
    expect(files.dragMove.canDrag(fileId)).toBe(true);
  });

  test('requires destination update eligibility and never drags folders or targets files', async (): Promise<void> => {
    const { api, files } = await setup(destinationId);
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    expect(files.dragMove.canDrag(destinationId)).toBe(false);
    const folderStart = drag(transfer());
    files.dragMove.start(destinationId, folderStart);
    expect(folderStart.preventDefault).toHaveBeenCalledOnce();
    for (const id of [destinationId, otherFileId]) {
      const data = start(files);
      files.dragMove.over(id, drag(data));
      expect(files.dragMove.isTarget(id)).toBe(false);
      expect(data.dropEffect).toBe('none');
      files.dragMove.drop(id, drag(data));
    }
    expect(patch).not.toHaveBeenCalled();
  });

  test.each(['forged', 'foreign', 'mismatched', 'os-files'])('ignores %s transfers without mutation', async (kind): Promise<void> => {
    const { api, files } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const data = kind === 'forged' ? transfer() : start(files);
    if (kind === 'foreign') data.types.splice(0, data.types.length, 'text/plain');
    else data.setData(fileMoveTransferType, kind === 'mismatched' ? otherFileId : fileId);
    if (kind === 'os-files') data.types.push('Files');
    const over = drag(data);
    const drop = drag(data);
    files.dragMove.over(destinationId, over);
    files.dragMove.drop(destinationId, drop);
    if (kind !== 'mismatched') {
      expect(over.preventDefault).not.toHaveBeenCalled();
      expect(drop.preventDefault).not.toHaveBeenCalled();
    }
    expect(files.dragMove.pending).toBe(false);
    expect(patch).not.toHaveBeenCalled();
  });

  test('blocks pending and uncertain sources until explicit reload', async (): Promise<void> => {
    const { api, files } = await setup();
    const response = deferred<NodeSummary>();
    const patch = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    const data = start(files);
    files.dragMove.drop(destinationId, drag(data));
    await vi.waitFor((): void => expect(patch).toHaveBeenCalledOnce());
    expect(files.dragMove.pending).toBe(true);
    expect(files.dragMove.canDrag(fileId)).toBe(false);
    const duplicate = drag(transfer());
    files.dragMove.start(fileId, duplicate);
    expect(duplicate.preventDefault).toHaveBeenCalledOnce();
    response.reject(new Error('Connection lost'));
    await vi.waitFor((): void => expect(files.dragMove.needsReload).toBe(true));
    expect(files.dragMove.canDrag(fileId)).toBe(false);
    expect(files.dragMove.error).toContain('Reload');
    expect(patch).toHaveBeenCalledOnce();
    await files.dragMove.reload();
    await vi.waitFor((): void => expect(files.dragMove.canDrag(fileId)).toBe(true));
    expect(files.dragMove.error).toBe('');
  });

  test('reports authoritative conflicts without removing the source', async (): Promise<void> => {
    const { api, files } = await setup();
    await api.filesystem.createFolder(destinationId, { name: 'Notes.txt', metadata: { content_type: {}, attributes: {} } });
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    files.dragMove.drop(destinationId, drag(start(files)));
    await vi.waitFor((): void => expect(files.dragMove.error).toContain('conflicts'));
    expect(patch).toHaveBeenCalledOnce();
    expect(files.children.some((node): boolean => node.id === fileId)).toBe(true);
    expect(files.dragMove.needsReload).toBe(false);
    expect(files.dragMove.canDrag(fileId)).toBe(true);
  });

  test('rechecks destination authorization before writing', async (): Promise<void> => {
    const { api, files } = await setup();
    const data = start(files);
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    files.dragMove.drop(destinationId, drag(data));
    await vi.waitFor((): void => expect(files.dragMove.error).toContain('cannot move'));
    expect(patch).not.toHaveBeenCalled();
    expect(files.children.some((node): boolean => node.id === fileId)).toBe(true);
  });

  test('navigation during destination checks cancels the write and stale notices', async (): Promise<void> => {
    const { api, files } = await setup();
    const gate = deferred<void>();
    vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockReturnValueOnce(gate.promise);
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    files.dragMove.drop(destinationId, drag(start(files)));
    expect(files.dragMove.pending).toBe(true);
    await files.load(rootId);
    gate.resolve();
    await gate.promise;
    await Promise.resolve();
    expect(patch).not.toHaveBeenCalled();
    expect(files.dragMove.status).toBe('');
    expect(files.dragMove.error).toBe('');
    expect(files.dragMove.pending).toBe(false);
  });

  test('navigation during mutation reconciles destination contents without a stale notice', async (): Promise<void> => {
    const { api, files } = await setup();
    const gate = deferred<void>();
    const original = api.filesystem.updateNode;
    const patch = vi.spyOn(api.filesystem, 'updateNode').mockImplementation(async (id, revision, input): Promise<NodeSummary> => {
      await gate.promise;
      return original(id, revision, input);
    });
    files.dragMove.drop(destinationId, drag(start(files)));
    await vi.waitFor((): void => expect(patch).toHaveBeenCalledOnce());
    await files.load(destinationId);
    expect(files.children).toEqual([]);
    gate.resolve();
    await vi.waitFor((): void => expect(files.children).toMatchObject([{ id: fileId, parent_id: destinationId, revision: 2 }]));
    expect(files.dragMove.status).toBe('');
    expect(files.dragMove.error).toBe('');
    expect(files.dragMove.pending).toBe(false);
    await files.load(folderId);
    expect(files.children.some((node): boolean => node.id === fileId)).toBe(false);
    expect(patch).toHaveBeenCalledOnce();
  });
});
