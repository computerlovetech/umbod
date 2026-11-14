import { afterEach, describe, expect, test, vi } from 'vitest';
import { flushSync, mount, tick, unmount } from 'svelte';
import { HttpError } from '$lib/admin/infrastructure/transport';
import { deferred, fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import type { NodeSummary } from '$lib/files/domain/schemas';
import FilesContent from './FilesContent.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;

afterEach(async (): Promise<void> => {
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  files = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate) => (candidate.getAttribute('aria-label') ?? candidate.textContent?.trim()) === label);
  expect(found, label).toBeDefined();
  return found!;
}

async function setup(id: string, denied = false): Promise<{ api: InMemoryFilesApi; state: FilesState }> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture, undefined, undefined, undefined, () => !denied);
  if (id === rootId) {
    const namespaces = await api.filesystem.listNamespaces();
    vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue(namespaces.map((namespace) => ({ ...namespace, kind: 'shared' as const, name: 'Research' })));
  }
  const state = new FilesState(api);
  files = state;
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
  await state.load(id);
  await tick();
  return { api, state };
}

async function edit(value: string): Promise<void> {
  document.querySelector<HTMLButtonElement>('[aria-label="Location actions"] button[aria-haspopup="menu"]')!.click();
  await tick();
  button('Edit description').click();
  await tick();
  const textarea = document.querySelector<HTMLTextAreaElement>('textarea')!;
  expect(document.querySelector(`label[for="${textarea.id}"]`)?.textContent).toBe('Description');
  expect(document.getElementById(textarea.getAttribute('aria-describedby')!)?.textContent).toBe('What is here, and when should it be read?');
  textarea.value = value;
  textarea.dispatchEvent(new Event('input', { bubbles: true }));
  flushSync();
}

function submit(): void {
  document.querySelector('form[aria-label="Edit description"]')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

describe('filesystem description UI', (): void => {
  test('folder and file navigation retain the same header and action slots without showing descriptions', async (): Promise<void> => {
    const { api, state } = await setup(folderId);
    for (const node of filesystemFixture) api.sharing.configure({ node_id: node.id, revision: 'revision', grants: [], blocked_recipients: [] }, []);
    for (const id of [folderId, fileId]) {
      const node = await api.filesystem.getNode(id);
      await api.filesystem.updateDescription(id, node.revision, { description: 'Project guidance' });
    }
    await state.reload();
    await vi.waitFor((): void => expect(state.sharing.available(folderId)).toBe(true));
    await tick();
    const container = document.querySelector('.page-container')!;
    const header = container.querySelector('header')!;
    const toolbar = container.querySelector('[aria-label="Location actions"]')!;
    const actionSlot = toolbar;
    const detail = container.querySelector('[aria-label="Files content"]')!;
    const retainedContent = detail.querySelector('[aria-busy]')!;
    expect(detail.querySelector('[aria-label="Description"]')).toBeNull();
    expect(detail.textContent).not.toContain('Project guidance');
    expect(detail.contains(header)).toBe(false);
    expect(detail.contains(toolbar)).toBe(false);
    expect(toolbar.querySelector('button[aria-label^="Share"]')).toBeNull();
    expect(actionSlot.querySelector('button[aria-label="Upload file"]')).not.toBeNull();
    expect(actionSlot.querySelector('button[aria-label="New folder"]')).not.toBeNull();
    expect(container.querySelector('table')).not.toBeNull();
    await state.load(fileId);
    await vi.waitFor((): void => expect(state.sharing.available(fileId)).toBe(true));
    await tick();
    expect(document.querySelector('.page-container')).toBe(container);
    expect(container.querySelector('header')).toBe(header);
    expect(container.querySelector('[aria-label="Location actions"]')).toBe(toolbar);
    expect(container.querySelector('[aria-label="Files content"]')).toBe(detail);
    expect(detail.querySelector('[aria-busy]')).toBe(retainedContent);
    expect(detail.querySelector('[aria-label="Description"]')).toBeNull();
    expect(detail.textContent).not.toContain('Project guidance');
    expect(actionSlot.textContent).not.toContain('Delete file');
    const trigger = actionSlot.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]');
    expect(trigger).not.toBeNull();
    trigger!.click();
    await tick();
    expect(document.querySelector('[role="menuitem"][aria-label="Share “Notes.txt”"]')).not.toBeNull();
    expect(document.querySelector('[role="menuitem"][aria-label="Delete “Notes.txt”"]')).not.toBeNull();
    expect(actionSlot.querySelector('button[aria-label="Upload file"]')).toBeNull();
    expect(container.querySelector('table')).toBeNull();
    expect(container.querySelector('[aria-label="Metadata"]')).not.toBeNull();
  });

  test('edits the row description through its actions menu and restores focus on cancellation', async (): Promise<void> => {
    const { api, state } = await setup(folderId);
    await vi.waitFor(() => expect(state.rowEditing.controllers.get(fileId)?.description.available).toBe(true));
    await tick();
    const trigger = document.querySelector<HTMLButtonElement>('tbody button[aria-haspopup="menu"]')!;
    const openEditor = async (): Promise<void> => {
      trigger.click();
      await tick();
      button('Edit description').click();
      await tick();
      expect(document.querySelector('[role="menu"]')).toBeNull();
      expect(document.querySelector('dialog textarea')).not.toBeNull();
    };
    await openEditor();
    button('Cancel').click();
    await tick();
    expect(document.activeElement).toBe(trigger);
    await openEditor();
    const textarea = document.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = 'Row guidance';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    submit();
    await vi.waitFor(() => expect(document.querySelector('dialog')).toBeNull());
    expect(document.querySelector('tbody')?.textContent).not.toContain('Row guidance');
    expect(document.querySelector('tbody [role="status"]')?.textContent).toBe('Description saved.');
    expect(trigger.getAttribute('aria-expanded')).toBe('false');
    expect(document.activeElement).toBe(trigger);
    expect((await api.filesystem.getNode(fileId)).metadata.attributes.description).toBe('Row guidance');
    expect((await api.filesystem.getNode(folderId)).metadata.attributes.description).toBeUndefined();
  });

  test.each([rootId, fileId, folderId])('edits, cancels and clears current %s without replacing heading', async (id): Promise<void> => {
    const { api, state } = await setup(id);
    await vi.waitFor(() => expect(state.description.available).toBe(true));
    const heading = document.querySelector('h1');
    await edit('Cancelled');
    button('Cancel').click();
    await tick();
    expect(state.description.description).toBe('');
    await edit('Guidance');
    submit();
    await vi.waitFor(() => expect(document.querySelector('textarea')).toBeNull());
    expect(document.querySelector('[aria-label="Description"]')).toBeNull();
    expect((await api.filesystem.getNode(id)).metadata.attributes.description).toBe('Guidance');
    expect(document.querySelector('h1')).toBe(heading);
    await edit('');
    submit();
    await vi.waitFor(() => expect(state.description.description).toBe(''));
    expect((await api.filesystem.getNode(id)).metadata.attributes).not.toHaveProperty('description');
  });

  test('root browsing uses current canonical metadata even when namespace discovery is stale', async (): Promise<void> => {
    const { api, state } = await setup(rootId);
    const namespaces = await api.filesystem.listNamespaces();
    vi.spyOn(api.filesystem, 'listNamespaces').mockResolvedValue(namespaces.map((namespace) => ({ ...namespace, description: 'Stale inventory description' })));
    const root = await api.filesystem.getNode(rootId);
    await api.filesystem.updateDescription(rootId, root.revision, { description: 'Canonical namespace description' });
    await state.reload();
    await tick();
    expect(document.body.textContent).not.toContain('Canonical namespace description');
    await edit('Canonical namespace description');
    expect(document.querySelector('textarea')?.value).toBe('Canonical namespace description');
    button('Cancel').click();
    await tick();
    expect(document.body.textContent).not.toContain('Stale inventory description');
    await edit('Updated from Files');
    submit();
    await vi.waitFor(() => expect(document.querySelector('textarea')).toBeNull());
    expect(document.querySelector('[aria-label="Description"]')).toBeNull();
    expect((await api.filesystem.getNode(rootId)).metadata.attributes.description).toBe('Updated from Files');
  });

  test('denied editing and inline descriptions stay hidden in the opened item', async (): Promise<void> => {
    const { api, state } = await setup(folderId);
    await api.filesystem.updateDescription(fileId, 1, { description: 'Row guidance' });
    await state.reload();
    await tick();
    expect(document.querySelector('tbody')?.textContent).not.toContain('Row guidance');
    vi.spyOn(api.filesystem, 'checkDescriptionEligibility').mockRejectedValue(new HttpError(403, 'Forbidden', {}));
    await state.load(fileId);
    await tick();
    expect(document.querySelector('[aria-label="Description"]')).toBeNull();
    expect(document.body.textContent).not.toContain('Row guidance');
    const labels = Array.from(document.querySelectorAll('button')).map((candidate) => candidate.textContent?.trim());
    expect(labels).not.toContain('Edit description');
    expect(labels).not.toContain('Retry description check');
    expect(labels).not.toContain('Reload item');
  });

  test('blocks pending duplicates, shows conflict recovery and reloads only by explicit action', async (): Promise<void> => {
    const { api, state } = await setup(fileId);
    await edit('My draft');
    const response = deferred<NodeSummary>();
    const update = vi.spyOn(api.filesystem, 'updateDescription').mockReturnValueOnce(response.promise);
    submit();
    submit();
    await tick();
    expect(button('Saving…').disabled).toBe(true);
    expect(button('Cancel').disabled).toBe(true);
    expect(document.querySelector('textarea')?.disabled).toBe(true);
    expect(update).toHaveBeenCalledTimes(1);
    response.reject(new HttpError(412, 'Conflict', {}));
    await vi.waitFor(() => expect(state.description.needsReload).toBe(true));
    await tick();
    expect(document.querySelector('textarea')?.value).toBe('My draft');
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('changed');
    expect(button('Save description').disabled).toBe(true);
    button('Reload item').click();
    await vi.waitFor(() => expect(state.description.needsReload).toBe(false));
    await tick();
    expect(document.querySelector('textarea')).toBeNull();
  });

  test('upload description input forwards user text into published metadata', async (): Promise<void> => {
    const { state } = await setup(folderId);
    await vi.waitFor(() => expect(state.uploadAvailability).toBe('allowed'));
    await tick();
    button('Upload file').click();
    await tick();
    const picker = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(picker, 'files', { value: [new File(['text'], 'Described.txt')], configurable: true });
    picker.dispatchEvent(new Event('change', { bubbles: true }));
    const textarea = document.querySelector<HTMLTextAreaElement>('dialog textarea')!;
    textarea.value = 'Upload guidance';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    document.querySelector('form[aria-label="Upload file"]')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(state.children.find((node) => node.name === 'Described.txt')?.metadata.attributes.description).toBe('Upload guidance'));
  });

  test('folder creation description input forwards user text', async (): Promise<void> => {
    const { state } = await setup(folderId);
    button('New folder').click();
    await tick();
    const name = document.querySelector<HTMLInputElement>('#folder-name')!;
    name.value = 'New';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    const description = document.querySelector<HTMLTextAreaElement>('#folder-description')!;
    description.value = 'Creation guidance';
    description.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    document.querySelector('form[aria-label="New folder"]')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    await vi.waitFor(() => expect(state.children.find((node) => node.name === 'New')?.metadata.attributes.description).toBe('Creation guidance'));
  });
});
