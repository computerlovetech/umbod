import { mount, tick, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest';
import { NetworkError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '$lib/files/api';
import { deferred, filesystemFixture, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api.test-support';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FileUploadForm from './FileUploadForm.svelte';

let component: ReturnType<typeof mount> | undefined;
let uploadState: UploadState | undefined;
let filesState: FilesState | undefined;

beforeEach((): void => {
  let sequence = 0;
  vi.spyOn(URL, 'createObjectURL').mockImplementation((): string => `blob:upload-${++sequence}`);
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation((): void => {});
});

afterEach(async (): Promise<void> => {
  try {
    if (component) await unmount(component);
  } finally {
    uploadState?.dispose();
    filesState?.dispose();
    component = undefined;
    uploadState = undefined;
    filesState = undefined;
    document.body.replaceChildren();
    vi.restoreAllMocks();
  }
});

async function fixture(): Promise<{ api: FilesApi; files: FilesState; upload: UploadState }> {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  const upload = new UploadState(api, files);
  filesState = files;
  uploadState = upload;
  await files.load(null);
  await vi.waitFor((): void => expect(upload.available).toBe(true));
  upload.show();
  component = mount(FileUploadForm, { target: document.body, props: { state: upload, destination: 'Projects', signIn: vi.fn() } });
  await tick();
  return { api, files, upload };
}

function requiredElement<T extends Element>(selector: string): T {
  const element = document.querySelector<T>(selector);
  expect(element).not.toBeNull();
  if (!element) throw new Error(`Missing element: ${selector}`);
  return element;
}

function picker(label: 'Choose file' | 'Change file'): HTMLInputElement {
  const labels = Array.from(document.querySelectorAll('label')).filter((element: HTMLLabelElement): boolean => element.textContent?.trim() === label);
  expect(labels).toHaveLength(1);
  const control = labels[0].control;
  expect(control).toBeInstanceOf(HTMLInputElement);
  if (!(control instanceof HTMLInputElement)) throw new Error('Missing native file picker');
  expect(control.type).toBe('file');
  expect(document.querySelectorAll('input[type="file"]')).toHaveLength(1);
  return control;
}

async function choose(input: HTMLInputElement, file: File): Promise<void> {
  Object.defineProperty(input, 'files', { configurable: true, value: [file] });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  await tick();
}

async function dropFiles(files: readonly File[]): Promise<void> {
  const transfer = new DataTransfer();
  for (const file of files) transfer.items.add(file);
  Object.defineProperty(transfer, 'types', { value: ['Files'] });
  const event = new Event('drop', { bubbles: true, cancelable: true });
  Object.defineProperty(event, 'dataTransfer', { value: transfer });
  requiredElement<HTMLElement>('[role="group"][aria-label="File drop area"]').dispatchEvent(event);
  await tick();
}

function action(name: string): HTMLButtonElement {
  const button = Array.from(document.querySelectorAll('button')).find((element: HTMLButtonElement): boolean => (element.getAttribute('aria-label') ?? element.textContent?.trim()) === name);
  expect(button).toBeDefined();
  if (!button) throw new Error(`Missing action: ${name}`);
  return button;
}

describe('mounted upload selection', (): void => {
  test('replaces the empty prompt with selected details and keeps one relabelled native picker when replacing a file', async (): Promise<void> => {
    const { upload } = await fixture();
    const input = picker('Choose file');
    expect(document.body.textContent).toContain('Drag and drop a file here');
    expect(action('Upload file').disabled).toBe(true);
    await choose(input, new File(['first'], 'first.txt', { type: 'text/plain' }));
    expect(picker('Change file')).toBe(input);
    expect(document.body.textContent).not.toContain('Drag and drop a file here');
    expect(document.body.textContent).toContain('File selected');
    expect(document.body.textContent).toContain('first.txt');
    expect(document.body.textContent).toContain('5 bytes');
    expect(action('Remove file').type).toBe('button');
    expect(action('Upload file').disabled).toBe(false);
    const rename = requiredElement<HTMLInputElement>('input[autocomplete="off"]');
    rename.value = 'renamed.txt';
    rename.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    expect(upload.name).toBe('renamed.txt');
    const replacement = new File(['x'.repeat(1024)], 'replacement.txt', { type: 'text/plain' });
    await choose(picker('Change file'), replacement);
    expect(upload.file).toBe(replacement);
    expect(rename.value).toBe('replacement.txt');
    expect(document.body.textContent).toContain('1 KiB');
    expect(document.body.textContent).not.toContain('first.txt');
    expect(picker('Change file')).toBe(input);
  });

  test('removes a file, restores the empty prompt and focuses the native picker before selecting the same file again', async (): Promise<void> => {
    const { upload } = await fixture();
    const file = new File(['same'], 'same.txt');
    const input = picker('Choose file');
    await choose(input, file);
    expect(input.value).toBe('');
    action('Remove file').click();
    await tick();
    expect(upload.file).toBeUndefined();
    expect(picker('Choose file')).toBe(input);
    expect(document.activeElement).toBe(input);
    expect(document.body.textContent).toContain('Drag and drop a file here');
    expect(document.querySelector('button[aria-label="Remove file"]')).toBeNull();
    expect(document.querySelector('input[autocomplete="off"]')).toBeNull();
    expect(action('Upload file').disabled).toBe(true);
    await choose(input, file);
    expect(upload.file).toBe(file);
    expect(picker('Change file')).toBe(input);
    expect(action('Upload file').disabled).toBe(false);
    expect(input.value).toBe('');
  });

  test('reselecting the same file resets an edited upload name through the native change handler', async (): Promise<void> => {
    const { upload } = await fixture();
    const file = new File(['same'], 'same.txt');
    await choose(picker('Choose file'), file);
    const name = requiredElement<HTMLInputElement>('input[autocomplete="off"]');
    name.value = 'different.txt';
    name.dispatchEvent(new Event('input', { bubbles: true }));
    await tick();
    expect(upload.name).toBe('different.txt');
    await choose(picker('Change file'), file);
    expect(name.value).toBe('same.txt');
    expect(upload.name).toBe('same.txt');
  });

  test('accepts a dropped replacement and retains it when a subsequent multi-file drop is rejected', async (): Promise<void> => {
    const { upload } = await fixture();
    await choose(picker('Choose file'), new File(['old'], 'old.txt'));
    const replacement = new File(['new'], 'dropped.txt');
    await dropFiles([replacement]);
    expect(upload.file).toBe(replacement);
    expect(document.body.textContent).toContain('dropped.txt');
    expect(document.body.textContent).not.toContain('old.txt');
    expect(picker('Change file')).toBeDefined();
    await dropFiles([new File([], 'one.txt'), new File([], 'two.txt')]);
    expect(requiredElement<HTMLElement>('[role="alert"]').textContent).toMatch(/one file at a time/i);
    expect(upload.file).toBe(replacement);
    expect(document.body.textContent).toContain('dropped.txt');
    expect(action('Upload file').disabled).toBe(true);
  });

  test.each([
    { name: 'empty.txt', type: 'text/plain', content: '', size: '0 bytes', icon: 'Text file' },
    { name: 'document.pdf', type: 'application/pdf', content: 'pdf', size: '3 bytes', icon: 'PDF file' },
    { name: 'vector.svg', type: 'image/svg+xml', content: '<svg/>', size: '6 bytes', icon: 'Image file' },
    { name: 'unknown.bin', type: '', content: 'data', size: '4 bytes', icon: 'File' }
  ])('keeps $name uploadable with a type icon and no object URL', async ({ name, type, content, size, icon }): Promise<void> => {
    const { upload } = await fixture();
    const file = new File([content], name, { type });
    await choose(picker('Choose file'), file);
    expect(upload.file).toBe(file);
    expect(document.body.textContent).toContain(size);
    expect(document.querySelector('img')).toBeNull();
    expect(requiredElement<SVGElement>(`svg[role="img"][aria-label="${icon}"]`)).toBeDefined();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(action('Upload file').disabled).toBe(false);
  });
});

describe('mounted upload thumbnails', (): void => {
  test.each(['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/avif', 'image/bmp'])('creates a preview from %s MIME even without an image filename and revokes it on unmount', async (type: string): Promise<void> => {
    await fixture();
    const file = new File(['image'], 'upload.bin', { type });
    await choose(picker('Choose file'), file);
    expect(URL.createObjectURL).toHaveBeenCalledExactlyOnceWith(file);
    expect(requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').getAttribute('src')).toBe('blob:upload-1');
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
    expect(action('Upload file').disabled).toBe(false);
    if (!component) throw new Error('Missing mounted component');
    await unmount(component);
    component = undefined;
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:upload-1');
  });

  test('revokes each replaced or removed image URL without revoking the active preview early', async (): Promise<void> => {
    await fixture();
    await choose(picker('Choose file'), new File(['one'], 'one.png', { type: 'image/png' }));
    await dropFiles([new File(['two'], 'two.jpg', { type: 'image/jpeg' })]);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:upload-1');
    expect(requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').getAttribute('src')).toBe('blob:upload-2');
    await choose(picker('Change file'), new File(['text'], 'text.txt', { type: 'text/plain' }));
    expect(document.querySelector('img')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenNthCalledWith(2, 'blob:upload-2');
    await choose(picker('Change file'), new File(['three'], 'three.png', { type: 'image/png' }));
    action('Remove file').click();
    await tick();
    expect(document.querySelector('img')).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(3);
    expect(URL.revokeObjectURL).toHaveBeenNthCalledWith(3, 'blob:upload-3');
    expect(document.activeElement).toBe(picker('Choose file'));
  });

  test('ignores a stale decode error from a replaced preview', async (): Promise<void> => {
    const { upload } = await fixture();
    await choose(picker('Choose file'), new File(['old'], 'old.png', { type: 'image/png' }));
    const previous = requiredElement<HTMLImageElement>('img[alt="Selected file preview"]');
    const replacement = new File(['new'], 'new.png', { type: 'image/png' });
    await choose(picker('Change file'), replacement);
    expect(previous.isConnected).toBe(false);
    previous.dispatchEvent(new Event('error'));
    await tick();
    expect(upload.file).toBe(replacement);
    expect(requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').getAttribute('src')).toBe('blob:upload-2');
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:upload-1');
    expect(action('Upload file').disabled).toBe(false);
  });

  test('falls back to the image type icon after decode failure without rejecting the upload and allows a new preview', async (): Promise<void> => {
    const { upload } = await fixture();
    const file = new File(['not an image'], 'broken.png', { type: 'image/png' });
    await choose(picker('Choose file'), file);
    requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').dispatchEvent(new Event('error'));
    await tick();
    expect(document.querySelector('img')).toBeNull();
    expect(requiredElement<SVGElement>('svg[role="img"][aria-label="Image file"]')).toBeDefined();
    expect(URL.revokeObjectURL).toHaveBeenCalledExactlyOnceWith('blob:upload-1');
    expect(upload.file).toBe(file);
    expect(upload.error).toBe('');
    expect(document.querySelector('[role="alert"]')).toBeNull();
    expect(action('Upload file').disabled).toBe(false);
    await choose(picker('Change file'), new File(['new'], 'new.png', { type: 'image/png' }));
    expect(requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').getAttribute('src')).toBe('blob:upload-2');
    expect(URL.createObjectURL).toHaveBeenCalledTimes(2);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
  });
});

test('locks picker, removal and drops during pending and uncertain uploads while preserving the selected preview', async (): Promise<void> => {
  const { api, upload } = await fixture();
  const result = deferred<never>();
  const request = vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(result.promise);
  const file = new File(['image'], 'pending.png', { type: 'image/png' });
  await choose(picker('Choose file'), file);
  action('Upload file').click();
  await tick();
  expect(request).toHaveBeenCalledTimes(1);
  expect(upload.pending).toBe(true);
  expect(requiredElement<HTMLFormElement>('form').getAttribute('aria-busy')).toBe('true');
  expect(requiredElement<HTMLFieldSetElement>('fieldset').disabled).toBe(true);
  expect(picker('Change file').closest('fieldset')?.disabled).toBe(true);
  expect(action('Remove file').closest('fieldset')?.disabled).toBe(true);
  expect(action('Cancel').disabled).toBe(true);
  expect(action('Uploading…').disabled).toBe(true);
  expect(requiredElement<HTMLProgressElement>('progress').getAttribute('aria-label')).toBe('Uploading file');
  action('Remove file').click();
  await dropFiles([new File(['replacement'], 'replacement.txt')]);
  expect(upload.file).toBe(file);
  result.reject(new NetworkError('lost response'));
  await vi.waitFor((): void => expect(upload.uncertain).toBe(true));
  await tick();
  expect(upload.pending).toBe(false);
  expect(requiredElement<HTMLFieldSetElement>('fieldset').disabled).toBe(true);
  expect(picker('Change file').closest('fieldset')?.disabled).toBe(true);
  expect(action('Remove file').closest('fieldset')?.disabled).toBe(true);
  expect(action('Upload file').disabled).toBe(true);
  expect(action('Reload folder').disabled).toBe(false);
  expect(action('Close').disabled).toBe(false);
  expect(document.querySelector('progress')).toBeNull();
  action('Remove file').click();
  await dropFiles([new File([], 'blocked.txt')]);
  expect(upload.file).toBe(file);
  expect(requiredElement<HTMLImageElement>('img[alt="Selected file preview"]').getAttribute('src')).toBe('blob:upload-1');
  expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  expect(request).toHaveBeenCalledTimes(1);
});
