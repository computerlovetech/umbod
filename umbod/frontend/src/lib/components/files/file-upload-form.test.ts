import { Window } from 'happy-dom';
import { render } from 'svelte/server';
import { describe, expect, test, vi } from 'vitest';
import { AuthenticationRequiredError, NetworkError } from '$lib/admin/infrastructure/transport';
import type { FilesApi } from '$lib/files/api';
import { deferred, filesystemFixture, rootId } from '$lib/files/fixtures.test-support';
import { InMemoryFilesApi } from '$lib/files/infrastructure/in-memory-api';
import { FilesState } from '$lib/files/state/files-state.svelte';
import { UploadState } from '$lib/files/state/upload-state.svelte';
import FileUploadForm from './FileUploadForm.svelte';

async function fixture(): Promise<{ api: FilesApi; files: FilesState; upload: UploadState }> {
  const api: FilesApi = new InMemoryFilesApi(rootId, filesystemFixture);
  const files = new FilesState(api);
  const upload = new UploadState(api, files);
  await files.load(null);
  await vi.waitFor(() => expect(upload.available).toBe(true));
  upload.show();
  return { api, files, upload };
}

function formDocument(state: UploadState): Window['document'] {
  const window = new Window();
  window.document.body.innerHTML = render(FileUploadForm, { props: { state, destination: 'Projects', signIn: vi.fn() } }).body;
  return window.document;
}

describe('upload form server-rendered accessibility', () => {
  test('uses one native modal dialog labelled by its heading and described by its destination', async (): Promise<void> => {
    const { upload } = await fixture();
    const document = formDocument(upload);
    const dialogs = document.querySelectorAll('dialog');
    expect(dialogs).toHaveLength(1);
    const dialog = dialogs[0];
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.hasAttribute('open')).toBe(false);
    const heading = document.getElementById(dialog.getAttribute('aria-labelledby') ?? '');
    const destination = document.getElementById(dialog.getAttribute('aria-describedby') ?? '');
    expect(heading?.tagName).toBe('H2');
    expect(heading?.textContent).toBe('Upload a file');
    expect(destination?.textContent).toBe('To Projects');
    expect(heading && dialog.contains(heading)).toBe(true);
    expect(destination && dialog.contains(destination)).toBe(true);
    expect(dialog.querySelector('form')).not.toBeNull();
    expect(document.querySelector('form')?.closest('dialog')).toBe(dialog);
    expect(dialog.querySelector('[role="status"]')?.getAttribute('aria-atomic')).toBe('true');
  });

  test('renders one labelled single-file native picker with unrestricted type and described guidance', async (): Promise<void> => {
    const { upload } = await fixture();
    const document = formDocument(upload);
    const form = document.querySelector('form');
    expect(form?.getAttribute('aria-label')).toBe('Upload file');
    expect(form?.getAttribute('aria-busy')).toBe('false');
    expect(document.querySelector('h2')?.textContent).toBe('Upload a file');
    expect(document.querySelector('.destination')?.textContent).toBe('To Projects');
    expect(document.querySelector('.limit')?.textContent).toContain('One file');
    expect(document.body.textContent).not.toContain('maximum');
    const pickers = document.querySelectorAll('input[type="file"]');
    expect(pickers).toHaveLength(1);
    const picker = pickers[0];
    expect(picker.hasAttribute('multiple')).toBe(false);
    expect(picker.hasAttribute('accept')).toBe(false);
    expect(picker.hasAttribute('disabled')).toBe(false);
    expect(picker.hasAttribute('hidden')).toBe(false);
    expect(document.querySelector(`label[for="${picker.id}"]`)?.textContent).toBe('Choose file');
    const hint = document.getElementById(picker.getAttribute('aria-describedby') ?? '');
    expect(hint?.textContent).toContain('Any file type, including empty files');
    expect(hint?.textContent).toContain('Folders and multiple files are not supported');
    const drop = document.querySelector('[role="group"]');
    expect(drop?.getAttribute('aria-label')).toBe('File drop area');
    expect(drop?.getAttribute('aria-describedby')).toBe(hint?.id);
    expect(document.querySelector('legend')?.textContent).toBe('Choose a file to upload');
    expect(document.querySelector('button[type="submit"]')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('progress')).toBeNull();
  });

  test.each([0, 1024])('selected %s-byte file exposes original name, size, rename label and non-overwrite guidance', async (size): Promise<void> => {
    const { upload } = await fixture();
    upload.select([new File(['x'.repeat(size)], 'Original.txt')]);
    upload.changeName('Renamed.txt');
    const document = formDocument(upload);
    expect(document.querySelector('.selected-file strong')?.textContent).toBe('Original.txt');
    expect(document.querySelector('.selected-file span')?.textContent).toBe(size === 0 ? '0 bytes' : '1 KiB');
    const picker = document.querySelector('input[type="file"]');
    expect(document.querySelector(`label[for="${picker?.id}"]`)?.textContent).toBe('Choose a different file');
    const name = document.querySelector('input[autocomplete="off"]');
    expect(name?.getAttribute('value')).toBe('Renamed.txt');
    expect(name?.hasAttribute('required')).toBe(true);
    expect(document.querySelector(`label[for="${name?.id}"]`)?.textContent).toBe('File name');
    expect(document.getElementById(name?.getAttribute('aria-describedby') ?? '')?.textContent).toContain('Existing files are never overwritten');
    expect(document.querySelector('dialog [role="status"]')?.textContent).toBe(upload.status);
    expect(document.querySelector('.selection button')?.textContent).toBe('Remove file');
    expect(document.querySelector('button[type="submit"]')?.hasAttribute('disabled')).toBe(false);
  });

  test('selection rejection renders an inline alert, retains selected details and disables upload', async (): Promise<void> => {
    const { upload } = await fixture();
    upload.select([new File(['x'], 'Keep.txt')]);
    upload.select([new File([], 'One.txt'), new File([], 'Two.txt')]);
    const document = formDocument(upload);
    expect(document.querySelector('dialog [role="alert"]')?.textContent).toMatch(/one file at a time/i);
    expect(document.querySelector('.selected-file strong')?.textContent).toBe('Keep.txt');
    expect(document.querySelector('button[type="submit"]')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('fieldset')?.hasAttribute('disabled')).toBe(false);
  });

  test('pending upload disables the fieldset, submit and cancel and exposes indeterminate progress', async (): Promise<void> => {
    const { api, upload } = await fixture();
    const result = deferred<never>();
    vi.spyOn(api.filesystem, 'uploadFile').mockReturnValueOnce(result.promise);
    upload.select([new File(['x'], 'Pending.txt')]);
    const pending = upload.submit();
    const document = formDocument(upload);
    expect(document.querySelector('form')?.getAttribute('aria-busy')).toBe('true');
    expect(document.querySelector('dialog [role="status"]')?.textContent).toBe('Uploading file…');
    expect(document.querySelector('fieldset')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('.selected-file strong')?.textContent).toBe('Pending.txt');
    const submit = document.querySelector('button[type="submit"]');
    expect(submit?.hasAttribute('disabled')).toBe(true);
    expect(submit?.textContent).toBe('Uploading…');
    const cancel = Array.from(document.querySelectorAll('button')).find((button) => button.textContent === 'Cancel');
    expect(cancel?.hasAttribute('disabled')).toBe(true);
    const progress = document.querySelector('progress');
    expect(progress?.getAttribute('aria-label')).toBe('Uploading file');
    expect(progress?.hasAttribute('value')).toBe(false);
    expect(document.querySelector('.progress')?.textContent).toContain('Keep this tab open until the upload is confirmed');
    expect(document.body.textContent).not.toContain('%');
    result.reject(new NetworkError('lost response'));
    await pending;
  });

  test('uncertain outcome disables fieldset and upload while preserving close and explicit reload controls', async (): Promise<void> => {
    const { api, upload } = await fixture();
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new NetworkError('lost response'));
    upload.select([new File(['x'], 'Unconfirmed.txt')]);
    await upload.submit();
    const document = formDocument(upload);
    expect(document.querySelector('fieldset')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('button[type="submit"]')?.hasAttribute('disabled')).toBe(true);
    expect(document.querySelector('[role="alert"]')?.textContent).toMatch(/confirm the upload/);
    expect(document.querySelector('.selected-file strong')?.textContent).toBe('Unconfirmed.txt');
    expect(document.querySelector('progress')).toBeNull();
    for (const label of ['Close', 'Reload folder']) {
      const button = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent === label);
      expect(button).toBeDefined();
      expect(button?.getAttribute('type')).toBe('button');
      expect(button?.hasAttribute('disabled')).toBe(false);
    }
  });

  test('authentication failure retains selection and exposes the sign-in action without leaking diagnostics', async (): Promise<void> => {
    const { api, upload } = await fixture();
    expect(formDocument(upload).body.textContent).not.toContain('Sign in');
    vi.spyOn(api.filesystem, 'uploadFile').mockRejectedValueOnce(new AuthenticationRequiredError());
    upload.select([new File(['x'], 'Keep.txt')]);
    await upload.submit();
    const document = formDocument(upload);
    const button = Array.from(document.querySelectorAll('button')).find((candidate) => candidate.textContent === 'Sign in');
    expect(button).toBeDefined();
    expect(button?.getAttribute('type')).toBe('button');
    expect(button?.hasAttribute('disabled')).toBe(false);
    expect(document.querySelector('[role="alert"]')?.textContent).toBe('Sign in to upload this file.');
    expect(document.querySelector('.selected-file strong')?.textContent).toBe('Keep.txt');
    expect(document.querySelector('fieldset')?.hasAttribute('disabled')).toBe(false);
    expect(document.body.textContent).not.toContain('AuthenticationRequiredError');
  });
});
