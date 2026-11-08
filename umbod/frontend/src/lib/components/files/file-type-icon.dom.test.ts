import { afterEach, describe, expect, test, vi } from 'vitest';
import { mount, tick, unmount } from 'svelte';
import { fileId, filesystemFixture, folderId, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { NewFolderState } from '$lib/files/state/new-folder-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FileTypeIcon from './FileTypeIcon.svelte';
import FilesContent from './FilesContent.svelte';

let component: ReturnType<typeof mount> | undefined;
let files: FilesState | undefined;

afterEach(async (): Promise<void> => {
  files?.dispose();
  if (component) await unmount(component);
  component = undefined;
  files = undefined;
  document.body.replaceChildren();
});

function mountTarget(): HTMLDivElement {
  const target = document.createElement('div');
  document.body.append(target);
  return target;
}

function button(label: string, scope: ParentNode = document): HTMLButtonElement {
  const found = Array.from(scope.querySelectorAll('button')).find((candidate) => candidate.textContent?.trim() === label);
  expect(found, label).toBeDefined();
  return found!;
}

describe('file type icons', (): void => {
  test.each([
    ['photo.PNG', 'Image file'], ['music.mp3', 'Audio file'], ['movie.mov', 'Video file'],
    ['report.pdf', 'PDF file'], ['notes.docx', 'Document file'], ['budget.xlsx', 'Spreadsheet file'],
    ['slides.pptx', 'Presentation file'], ['notes.txt', 'Text file'], ['script.py', 'Code file'],
    ['backup.tar.gz', 'Archive file'], ['unknown.bin', 'File']
  ])('renders %s with an accessible %s icon', async (name, label): Promise<void> => {
    component = mount(FileTypeIcon, { target: mountTarget(), props: { kind: 'file', name, contentType: {} } });
    await tick();
    const icon = document.querySelector('svg[role="img"]')!;
    expect(icon.getAttribute('aria-label')).toBe(label);
    expect(icon.getAttribute('width')).toBe('20');
    expect(icon.querySelector('path')).not.toBeNull();
    expect(icon.querySelector('image, use, script')).toBeNull();
  });

  test('renaming a file updates its row icon in place without changing navigation or actions', async (): Promise<void> => {
    const api = new InMemoryFilesApi(rootId, filesystemFixture);
    const state = new FilesState(api);
    files = state;
    component = mount(FilesContent, { target: mountTarget(), props: { state, folder: new NewFolderState(api, state), upload: new UploadState(api, state), signIn: vi.fn() } });
    await state.load(folderId);
    await vi.waitFor((): void => expect(state.rowEditing.controllers.get(fileId)?.update.canRename).toBe(true));
    await tick();
    const link = document.querySelector<HTMLAnchorElement>(`tbody a[href="/files?node=${fileId}"]`)!;
    const trigger = document.querySelector<HTMLButtonElement>('tbody button[aria-haspopup="menu"]')!;
    expect(link.querySelector('svg')?.getAttribute('aria-label')).toBe('Text file');
    trigger.click();
    await tick();
    button('Rename').click();
    await tick();
    const input = document.querySelector<HTMLInputElement>('dialog #node-rename')!;
    input.value = 'diagram.svg';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    button('Rename', document.querySelector('dialog')!).click();
    await vi.waitFor((): void => expect(link.querySelector('svg')?.getAttribute('aria-label')).toBe('Image file'));
    expect(link.textContent?.trim()).toBe('diagram.svg');
    expect(document.querySelector(`tbody a[href="/files?node=${fileId}"]`)).toBe(link);
    expect(document.querySelector('tbody button[aria-haspopup="menu"]')).toBe(trigger);
  });
});
