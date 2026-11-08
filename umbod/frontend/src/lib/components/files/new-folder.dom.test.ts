import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { filesystemFixture, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FilesContent from './FilesContent.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;
let folder: NewFolderState | undefined;
let upload: UploadState | undefined;

afterEach(async (): Promise<void> => {
  folder?.dispose();
  upload?.dispose();
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  files = undefined;
  folder = undefined;
  upload = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
});

function button(label: string): HTMLButtonElement {
  const found = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(found, label).toBeDefined();
  return found!;
}

async function setup(): Promise<InMemoryFilesApi> {
  const api = new InMemoryFilesApi(rootId, filesystemFixture);
  const state = new FilesState(api);
  files = state;
  folder = new NewFolderState(api, state);
  upload = new UploadState(api, state);
  const target = document.createElement('div');
  document.body.append(target);
  component = mount(FilesContent, { target, props: { state, folder, upload, signIn: vi.fn() } });
  await state.load(rootId);
  await tick();
  button('New folder').click();
  await tick();
  const input = document.querySelector<HTMLInputElement>('#folder-name')!;
  input.value = 'Created folder';
  input.dispatchEvent(new Event('input', { bubbles: true }));
  await tick();
  return api;
}

describe('new folder action buttons', (): void => {
  test('focuses the folder name after the native dialog opens', async (): Promise<void> => {
    vi.spyOn(HTMLDialogElement.prototype, 'showModal').mockImplementation(function (this: HTMLDialogElement): void {
      this.open = true;
      const title = this.querySelector<HTMLElement>('[data-dialog-title]');
      expect(title).not.toBeNull();
      title!.focus();
    });
    await setup();
    const dialog = document.querySelector('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog?.getAttribute('aria-modal')).toBe('true');
    expect(document.getElementById(dialog!.getAttribute('aria-labelledby')!)?.textContent).toBe('New folder');
    expect(dialog?.querySelector('form[aria-label="New folder"]')).not.toBeNull();
    expect(document.activeElement).toBe(document.getElementById('folder-name'));
  });

  test.each(['Cancel', 'Close', 'backdrop'])('%s dismisses the modal without creating a folder', async (label): Promise<void> => {
    const api = await setup();
    const create = vi.spyOn(api.filesystem, 'createFolder');
    const dismiss = label === 'backdrop'
      ? document.querySelector<HTMLDialogElement>('dialog')
      : label === 'Close'
        ? document.querySelector<HTMLButtonElement>('button[aria-label="Close"]')
        : button(label);
    expect(dismiss).not.toBeNull();
    if (label === 'backdrop') dismiss!.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: -10, clientY: -10 }));
    else dismiss!.click();
    await tick();
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(document.getElementById('new-folder-button')));
    expect(create).not.toHaveBeenCalled();
  });

  test.each(['Create folder', 'Cancel'])('Escape on %s cancels and restores the invoking button', async (label): Promise<void> => {
    const api = await setup();
    const create = vi.spyOn(api.filesystem, 'createFolder');
    const action = button(label);
    action.focus();
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true });
    action.dispatchEvent(escape);
    await tick();
    expect(escape.defaultPrevented).toBe(true);
    expect(document.querySelector('form[aria-label="New folder"]')).toBeNull();
    await vi.waitFor(() => expect(document.activeElement).toBe(document.getElementById('new-folder-button')));
    expect(create).not.toHaveBeenCalled();
  });

  test('native submit creates a folder and restores the invoking button', async (): Promise<void> => {
    const api = await setup();
    const create = vi.spyOn(api.filesystem, 'createFolder');
    const submit = button('Create folder');
    expect(submit.type).toBe('submit');
    expect(submit.form?.getAttribute('aria-label')).toBe('New folder');
    submit.click();
    await vi.waitFor(() => expect(document.querySelector('form[aria-label="New folder"]')).toBeNull());
    expect(create).toHaveBeenCalledOnce();
    expect(document.querySelector('tbody')?.textContent).toContain('Created folder');
    await vi.waitFor(() => expect(document.activeElement).toBe(document.getElementById('new-folder-button')));
  });
});
