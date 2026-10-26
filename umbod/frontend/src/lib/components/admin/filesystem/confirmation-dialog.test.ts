import { Window } from 'happy-dom';
import { describe, expect, it, vi } from 'vitest';
import { filesystemConfirmation } from './confirmation-dialog';
import { InMemoryGroupCatalogue } from '$lib/admin/groups/in-memory';
import { FilesystemAccessState } from './filesystem-access-state.svelte';
import { InMemoryFilesystemAdministration } from '$lib/admin/filesystem/in-memory';
import { rootPolicy } from '$lib/admin/filesystem/fixtures.test-support';

function dialogFixture(): { window: Window; document: Document; dialog: HTMLDialogElement; cancel: HTMLButtonElement; opener: HTMLButtonElement } {
  const window = new Window();
  const document = window.document as unknown as Document;
  const dialog = document.createElement('dialog');
  const cancel = document.createElement('button');
  cancel.dataset.dialogCancel = '';
  const confirm = document.createElement('button');
  const opener = document.createElement('button');
  dialog.append(cancel, confirm);
  document.body.append(opener, dialog);
  opener.focus();
  dialog.showModal = vi.fn(() => { dialog.setAttribute('open', ''); });
  dialog.close = vi.fn(() => { dialog.removeAttribute('open'); });
  return { window, document, dialog, cancel, opener };
}

describe('filesystem native confirmation lifecycle', () => {
  it('keeps registration modal open while an explicit registration is pending', (): void => {
    const { dialog, window } = dialogFixture();
    const cancel = vi.fn();
    const cleanup = filesystemConfirmation(cancel, () => false)(dialog);
    const event = new window.Event('cancel', { cancelable: true }) as unknown as Event;
    dialog.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(dialog.close).not.toHaveBeenCalled();
    expect(cancel).not.toHaveBeenCalled();
    if (typeof cleanup === 'function') cleanup();
  });

  it('opens natively modal, focuses Cancel and closes before teardown for native focus restoration', () => {
    const { document, dialog, cancel } = dialogFixture();
    const cleanup = filesystemConfirmation(vi.fn())(dialog);
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    expect(document.activeElement).toBe(cancel);
    if (typeof cleanup === 'function') cleanup();
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(dialog.isConnected).toBe(true);
    expect(dialog.open).toBe(false);
  });
  it('Escape closes the native dialog, cancels confirmation and preserves the draft without submitting', async () => {
    const api = new InMemoryFilesystemAdministration(rootPolicy({ status: 'ready', groups: [{ issuer: 'issuer', group_id: 'existing', permissions: ['read'] }] }));
    const replace = vi.spyOn(api, 'replaceRootAccess');
    const state = new FilesystemAccessState(api, new InMemoryGroupCatalogue());
    await state.load();
    state.remove(state.rows[0].id);
    await state.save();
    expect(state.confirmation).toBe('empty');
    const { dialog, window } = dialogFixture();
    const cleanup = filesystemConfirmation(state.cancelConfirmation)(dialog);
    const event = new window.Event('cancel', { cancelable: true }) as unknown as Event;
    dialog.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(state.confirmation).toBe(null);
    expect(state.rows).toEqual([]);
    expect(state.dirty).toBe(true);
    expect(replace).not.toHaveBeenCalled();
    if (typeof cleanup === 'function') cleanup();
    expect(dialog.close).toHaveBeenCalledTimes(1);
  });
  it('Escape during discard confirmation leaves edited values unchanged and removes listeners on teardown', async () => {
    const state = new FilesystemAccessState(new InMemoryFilesystemAdministration(rootPolicy()), new InMemoryGroupCatalogue());
    await state.load();
    state.add();
    state.edit(state.rows[0].id, 'group_id', 'keep-draft');
    state.requestReload();
    const { dialog, window } = dialogFixture();
    const cancel = vi.fn(state.cancelConfirmation);
    const cleanup = filesystemConfirmation(cancel)(dialog);
    dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }) as unknown as Event);
    expect(state.rows[0].group_id).toBe('keep-draft');
    expect(state.confirmation).toBe(null);
    if (typeof cleanup === 'function') cleanup();
    dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }) as unknown as Event);
    expect(cancel).toHaveBeenCalledTimes(1);
  });
});
