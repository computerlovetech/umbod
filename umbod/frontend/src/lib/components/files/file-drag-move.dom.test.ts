import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, filesystemNode, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import { fileMoveTransferType } from '$lib/files/state/drag-move-state.svelte';
import type { NodeSummary } from '$lib/files/domain/schemas';
import FilesContent from './FilesContent.svelte';

const destinationId = '00000000-0000-4000-8000-000000000004';
const otherFileId = '00000000-0000-4000-8000-000000000005';
let component: ReturnType<typeof mount> | undefined;
let state: FilesState | undefined;

beforeEach((): void => {
  vi.spyOn(DataTransfer.prototype, 'setDragImage').mockImplementation((): void => {});
});

afterEach(async (): Promise<void> => {
  state?.dispose();
  if (component) await unmount(component);
  component = undefined;
  state = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

async function setup(description = ''): Promise<{ api: InMemoryFilesApi; files: FilesState; upload: UploadState }> {
  const api = new InMemoryFilesApi(rootId, [...filesystemFixture.map((node): NodeSummary => node.id === fileId ? { ...node, metadata: { ...node.metadata, attributes: { description } } } : node),
    filesystemNode({ id: destinationId, parent_id: folderId, name: 'Archive' }),
    filesystemNode({ id: otherFileId, parent_id: folderId, name: 'Other.txt', kind: 'file' })
  ]);
  const files = new FilesState(api);
  state = files;
  const upload = new UploadState(api, files);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state: files, folder: new NewFolderState(api, files), upload, signIn: vi.fn() } });
  await files.load(folderId);
  await vi.waitFor((): void => {
    expect(files.dragMove.canDrag(fileId)).toBe(true);
    expect(files.rowEditing.controllers.get(destinationId)?.update.canRename).toBe(true);
    expect(upload.canDrop).toBe(true);
  });
  await tick();
  return { api, files, upload };
}

function row(id: string): HTMLTableRowElement {
  const found = document.querySelector<HTMLAnchorElement>(`tbody a[href="/files?node=${id}"]`)?.closest('tr');
  expect(found).not.toBeNull();
  expect(found).toBeDefined();
  return found!;
}

function dispatch(target: EventTarget, type: string, dataTransfer: DataTransfer, coordinates: Pick<DragEvent, 'clientX' | 'clientY'> = { clientX: 0, clientY: 0 }): DragEvent {
  const event = new Event(type, { bubbles: true, cancelable: true });
  Object.defineProperties(event, { dataTransfer: { value: dataTransfer }, clientX: { value: coordinates.clientX }, clientY: { value: coordinates.clientY } });
  target.dispatchEvent(event);
  return event as DragEvent;
}

function begin(): DataTransfer {
  const data = new DataTransfer();
  dispatch(row(fileId), 'dragstart', data);
  return data;
}

describe('file row drag move UI', (): void => {
  test('shows the dragged file icon and name beside the pointer instead of the native row image', async (): Promise<void> => {
    await setup();
    const data = new DataTransfer();
    const link = row(fileId).querySelector<HTMLAnchorElement>('a')!;
    const dragImage = document.querySelector<HTMLImageElement>('img.file-drag-image')!;
    expect(link.getAttribute('draggable')).toBe('false');
    expect(row(fileId).getAttribute('draggable')).toBe('true');
    expect(dragImage.getAttribute('draggable')).toBe('false');
    expect(dragImage.getAttribute('src')).toMatch(/^data:image\/gif;base64,/);
    expect(dragImage.width).toBe(1);
    expect(dragImage.height).toBe(1);
    dispatch(link, 'dragstart', data, { clientX: 100, clientY: 200 });
    await tick();
    const preview = document.querySelector<HTMLElement>('.file-drag-preview')!;
    expect(preview.textContent).toContain('Move file');
    expect(preview.textContent).toContain('Notes.txt');
    expect(preview.querySelector('svg')).not.toBeNull();
    expect(preview.getAttribute('aria-hidden')).toBe('true');
    expect(preview.style.getPropertyValue('--preview-x')).toBe('116px');
    expect(preview.style.getPropertyValue('--preview-y')).toBe('216px');
    expect(data.setDragImage).toHaveBeenCalledExactlyOnceWith(dragImage, 0, 0);
    expect(Array.from(data.types)).toEqual([fileMoveTransferType]);
    dispatch(window, 'dragover', data, { clientX: 200, clientY: 300 });
    await tick();
    expect(preview.style.getPropertyValue('--preview-x')).toBe('216px');
    expect(preview.style.getPropertyValue('--preview-y')).toBe('316px');
    dispatch(row(fileId), 'dragend', data);
    await tick();
    expect(document.querySelector('.file-drag-preview')).toBeNull();
  });

  test('keeps the preview inside the viewport and removes it on navigation', async (): Promise<void> => {
    const { files } = await setup();
    const data = begin();
    dispatch(window, 'dragover', data, { clientX: window.innerWidth, clientY: window.innerHeight });
    await tick();
    const preview = document.querySelector<HTMLElement>('.file-drag-preview')!;
    const x = Number.parseFloat(preview.style.getPropertyValue('--preview-x'));
    const y = Number.parseFloat(preview.style.getPropertyValue('--preview-y'));
    expect(x).toBeGreaterThanOrEqual(8);
    expect(x + 288).toBeLessThanOrEqual(window.innerWidth);
    expect(y + 64).toBeLessThanOrEqual(window.innerHeight);
    await files.load(rootId);
    await tick();
    expect(document.querySelector('.file-drag-preview')).toBeNull();
  });

  test('highlights an eligible folder and moves exactly once in place without triggering upload', async (): Promise<void> => {
    const { api, files, upload } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const uploadFile = vi.spyOn(api.filesystem, 'uploadFile');
    const list = vi.spyOn(api.filesystem, 'listChildren');
    const table = document.querySelector('table');
    const destination = row(destinationId);
    const other = row(otherFileId);
    expect(row(fileId).getAttribute('draggable')).toBe('true');
    expect(destination.getAttribute('draggable')).toBe('false');
    const data = begin();
    expect(data.getData(fileMoveTransferType)).toBe(fileId);
    await tick();
    expect(row(fileId).classList.contains('drag-source')).toBe(true);
    expect(document.querySelector('.drag-status')?.textContent).toContain('Drop “Notes.txt”');
    expect(dispatch(destination, 'dragover', data).defaultPrevented).toBe(true);
    await tick();
    expect(destination.classList.contains('drop-target')).toBe(true);
    expect(document.querySelector('.page-file-drop')).toBeNull();
    dispatch(destination, 'drop', data);
    dispatch(destination, 'drop', data);
    await vi.waitFor((): void => expect(files.dragMove.status).toBe('Moved “Notes.txt” to “Archive”.'));
    await tick();
    expect(patch).toHaveBeenCalledExactlyOnceWith(fileId, 1, { parent_id: destinationId });
    expect(document.querySelector(`tbody a[href="/files?node=${fileId}"]`)).toBeNull();
    expect(document.querySelector('table')).toBe(table);
    expect(row(destinationId)).toBe(destination);
    expect(row(otherFileId)).toBe(other);
    expect(destination.classList.contains('drop-target')).toBe(false);
    expect(list).not.toHaveBeenCalled();
    expect(uploadFile).not.toHaveBeenCalled();
    expect(upload.open).toBe(false);
    await files.load(destinationId);
    await tick();
    expect(row(fileId).textContent).toContain('Notes.txt');
  });

  test('restores focus to the destination when the focused source row is removed', async (): Promise<void> => {
    await setup();
    row(fileId).querySelector<HTMLAnchorElement>('a')!.focus();
    dispatch(row(destinationId), 'drop', begin());
    await vi.waitFor((): void => expect(document.querySelector(`tbody a[href="/files?node=${fileId}"]`)).toBeNull());
    await vi.waitFor((): void => expect(document.activeElement).toBe(row(destinationId).querySelector('a')));
  });

  test('clears native link payloads and cancels internal drops outside folders without navigation or uploads', async (): Promise<void> => {
    const { api, files, upload } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const data = new DataTransfer();
    data.setData('text/uri-list', 'http://localhost/files?node=' + fileId);
    data.setData('text/plain', 'Notes.txt');
    dispatch(row(fileId).querySelector('a')!, 'dragstart', data);
    expect(Array.from(data.types)).toEqual([fileMoveTransferType]);
    expect(dispatch(window, 'dragover', data).defaultPrevented).toBe(true);
    expect(data.dropEffect).toBe('none');
    expect(dispatch(window, 'drop', data).defaultPrevented).toBe(true);
    await tick();
    expect(files.dragMove.isSource(fileId)).toBe(false);
    expect(upload.open).toBe(false);
    expect(document.querySelector('.page-file-drop')).toBeNull();
    expect(patch).not.toHaveBeenCalled();
  });

  test.each(['dragend', 'Escape', 'blur'])('clears source and target on %s without a move', async (action): Promise<void> => {
    const { api } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const data = begin();
    dispatch(row(destinationId), 'dragover', data);
    await tick();
    expect(row(destinationId).classList.contains('drop-target')).toBe(true);
    if (action === 'Escape') window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    else window.dispatchEvent(new Event(action));
    await tick();
    expect(document.querySelector('.drag-source')).toBeNull();
    expect(document.querySelector('.file-drag-preview')).toBeNull();
    expect(document.querySelector('.drop-target')).toBeNull();
    expect(document.querySelector('.drag-status')?.textContent).toBe('');
    dispatch(row(destinationId), 'drop', data);
    expect(patch).not.toHaveBeenCalled();
  });

  test('row action buttons cannot initiate a move and file rows cannot receive one', async (): Promise<void> => {
    const { api } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const button = row(fileId).querySelector('button')!;
    const rejected = new DataTransfer();
    expect(dispatch(button, 'dragstart', rejected).defaultPrevented).toBe(true);
    expect(rejected.getData(fileMoveTransferType)).toBe('');
    const data = begin();
    dispatch(row(otherFileId), 'dragover', data);
    await tick();
    expect(row(otherFileId).classList.contains('drop-target')).toBe(false);
    dispatch(row(otherFileId), 'drop', data);
    expect(patch).not.toHaveBeenCalled();
  });

  test('requires completed source and parent checks and hides denied source dragging and target highlighting', async (): Promise<void> => {
    const { api, files } = await setup();
    const source = files.rowEditing.controllers.get(fileId)!.update;
    const destination = files.rowEditing.controllers.get(destinationId)!.update;
    const gate = deferred<void>();
    const original = api.filesystem.checkUpdateEligibility;
    const check = vi.spyOn(api.filesystem, 'checkUpdateEligibility').mockImplementation((id, signal): Promise<void> => id === folderId ? gate.promise : original(id, signal));
    const checking = source.checkEligibility();
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('false');
    const rejected = new DataTransfer();
    expect(dispatch(row(fileId), 'dragstart', rejected).defaultPrevented).toBe(true);
    gate.resolve();
    await checking;
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('true');
    check.mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    await destination.checkEligibility();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const data = begin();
    dispatch(row(destinationId), 'dragover', data);
    await tick();
    expect(document.querySelector('.drop-target')).toBeNull();
    dispatch(row(destinationId), 'drop', data);
    check.mockRejectedValueOnce(new HttpError(403, 'Forbidden', {}));
    await source.checkEligibility();
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('false');
    expect(dispatch(row(fileId), 'dragstart', new DataTransfer()).defaultPrevented).toBe(true);
    expect(patch).not.toHaveBeenCalled();
  });

  test('removes draggable eligibility while pending and exposes uncertain move recovery', async (): Promise<void> => {
    const { api, files } = await setup();
    const response = deferred<NodeSummary>();
    const patch = vi.spyOn(api.filesystem, 'updateNode').mockReturnValueOnce(response.promise);
    dispatch(row(destinationId), 'drop', begin());
    await vi.waitFor((): void => expect(patch).toHaveBeenCalledOnce());
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('false');
    expect(document.querySelector('.drag-status')?.textContent).toContain('Moving');
    response.reject(new Error('Disconnected'));
    await vi.waitFor((): void => expect(files.dragMove.needsReload).toBe(true));
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('false');
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('Reload');
    const reload = Array.from(document.querySelectorAll('button')).find((button): boolean => button.textContent?.trim() === 'Reload folder');
    expect(Array.from(document.querySelectorAll('button')).map((button): string => button.textContent?.trim() ?? '')).toContain('Reload folder');
    expect(reload).toBeDefined();
    reload!.click();
    await vi.waitFor((): void => expect(files.dragMove.canDrag(fileId)).toBe(true));
    await tick();
    expect(row(fileId).getAttribute('draggable')).toBe('true');
    expect(patch).toHaveBeenCalledOnce();
  });

  test.each(['window', 'folder'])('OS file drops on %s retain the upload overlay and upload to the current parent', async (target): Promise<void> => {
    const { api, files, upload } = await setup();
    const patch = vi.spyOn(api.filesystem, 'updateNode');
    const uploadFile = vi.spyOn(api.filesystem, 'uploadFile');
    begin();
    const data = new DataTransfer();
    const file = new File(['outside'], 'Outside.txt', { type: 'text/plain' });
    data.items.add(file);
    data.setData(fileMoveTransferType, fileId);
    Object.defineProperty(data, 'types', { value: ['Files', fileMoveTransferType] });
    Object.defineProperty(data, 'files', { value: [file] });
    const receiver = target === 'window' ? window : row(destinationId);
    dispatch(receiver, 'dragenter', data);
    await tick();
    expect(document.querySelector('.page-file-drop')?.textContent).toContain('Drop a file to upload');
    expect(document.querySelector('.page-file-drop')?.textContent).toContain('To Projects');
    dispatch(receiver, 'dragover', data);
    await tick();
    expect(document.querySelector('.drop-target')).toBeNull();
    dispatch(receiver, 'drop', data);
    await vi.waitFor((): void => expect(files.children.some((node): boolean => node.name === 'Outside.txt')).toBe(true));
    await tick();
    expect(document.querySelector('.page-file-drop')).toBeNull();
    expect(uploadFile).toHaveBeenCalledExactlyOnceWith(folderId, expect.objectContaining({ name: 'Outside.txt' }));
    expect(patch).not.toHaveBeenCalled();
    expect((await api.filesystem.getNode(fileId)).parent_id).toBe(folderId);
    expect(await api.filesystem.listChildren(destinationId)).toEqual([]);
    expect(upload.pending).toBe(false);
  });

  test('the list omits descriptions while file details group full text, metadata and actions', async (): Promise<void> => {
    const description = 'First line\n\nSecond line\t' + 'Detailed guidance '.repeat(20) + '\nFinal line';
    const { api, files } = await setup(description);
    api.sharing.configure({ node_id: fileId, revision: 'revision', grants: [], blocked_recipients: [] }, []);
    expect(row(fileId).textContent).not.toContain('First line');
    expect(document.querySelector('tbody')?.textContent).not.toContain(description);
    const link = row(fileId).querySelector<HTMLAnchorElement>('a')!;
    const destination = new URL(link.href).searchParams.get('node');
    await files.load(destination);
    await tick();
    expect(document.querySelector('table')).toBeNull();
    const details = document.querySelector('[aria-label="File details"]')!;
    expect(document.querySelector('[aria-label="Description"]')?.textContent).toContain(description);
    expect(document.querySelector('[aria-label="Description"] h2')?.textContent).toBe('Description');
    expect(details.querySelector('[aria-label="Metadata"] h2')?.textContent).toBe('Metadata');
    expect(details.querySelector('[aria-label="Metadata"] dl')?.textContent).toContain('Content type');
    await vi.waitFor((): void => expect(files.sharing.available(fileId)).toBe(true));
    await tick();
    const actions = document.querySelector('[role="group"][aria-label="Location actions"]')!;
    expect(actions).not.toBeNull();
    expect(actions.querySelector('button[aria-label="Share “Notes.txt”"]')).not.toBeNull();
    expect(actions.textContent).toContain('Delete file');
  });
});
