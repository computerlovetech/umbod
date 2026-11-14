import { Window } from 'happy-dom';
import { describe, expect, it, vi } from 'vitest';
import { nativeDialog } from './native-dialog';
import { nativeDialog as legacyNativeDialog } from '../../admin/group-permissions/shared/native-dialog';

function dialogFixture(): { document: Document; dialog: HTMLDialogElement; cancel: HTMLButtonElement; picker: HTMLInputElement; cancelEvent: () => Event } {
  const window = new Window();
  const document = window.document as unknown as Document;
  const dialog = document.createElement('dialog');
  const cancel = document.createElement('button');
  cancel.dataset.dialogCancel = '';
  const disabledPicker = document.createElement('input');
  disabledPicker.type = 'file';
  disabledPicker.disabled = true;
  const picker = document.createElement('input');
  picker.type = 'file';
  dialog.append(cancel, disabledPicker, picker);
  document.body.append(dialog);
  dialog.showModal = vi.fn((): void => { dialog.setAttribute('open', ''); });
  dialog.close = vi.fn((): void => { dialog.removeAttribute('open'); });
  return { document, dialog, cancel, picker, cancelEvent: (): Event => new window.Event('cancel', { cancelable: true }) as unknown as Event };
}

describe('shared native dialog attachment', (): void => {
  it('preserves the legacy helper export', (): void => {
    expect(legacyNativeDialog).toBe(nativeDialog);
  });

  it('opens modally and focuses Cancel by default', (): void => {
    const { document, dialog, cancel } = dialogFixture();
    const cleanup = nativeDialog(vi.fn())(dialog);
    expect(dialog.showModal).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(true);
    expect(document.activeElement).toBe(cancel);
    if (typeof cleanup === 'function') cleanup();
  });

  it('focuses Close rather than preselecting the first field when Cancel is not marked', (): void => {
    const { document, dialog, cancel, picker } = dialogFixture();
    cancel.removeAttribute('data-dialog-cancel');
    const header = document.createElement('header');
    const close = document.createElement('button');
    close.dataset.dialogClose = '';
    header.append(close);
    dialog.prepend(header);
    const cleanup = nativeDialog(vi.fn())(dialog);
    expect(document.activeElement).toBe(close);
    picker.focus();
    expect(document.activeElement).toBe(picker);
    if (typeof cleanup === 'function') cleanup();
  });

  it('focuses a chooser action rather than its heading or header close button', (): void => {
    const { document, dialog, cancel } = dialogFixture();
    dialog.replaceChildren();
    const header = document.createElement('header');
    const heading = document.createElement('h2');
    heading.tabIndex = -1;
    const close = document.createElement('button');
    header.append(heading, close);
    cancel.removeAttribute('data-dialog-cancel');
    dialog.append(header, cancel);
    const cleanup = nativeDialog(vi.fn())(dialog);
    expect(document.activeElement).toBe(cancel);
    if (typeof cleanup === 'function') cleanup();
  });

  it('sets initial focus without scrolling the form', (): void => {
    const { dialog, cancel } = dialogFixture();
    const focus = vi.spyOn(cancel, 'focus');
    const cleanup = nativeDialog(vi.fn())(dialog);
    expect(focus).toHaveBeenCalledWith({ preventScroll: true });
    if (typeof cleanup === 'function') cleanup();
  });

  it('focuses the enabled file input selected by the caller', (): void => {
    const { document, dialog, picker } = dialogFixture();
    const cleanup = nativeDialog(vi.fn(), () => true, 'input[type="file"]:not(:disabled)')(dialog);
    expect(document.activeElement).toBe(picker);
    if (typeof cleanup === 'function') cleanup();
  });

  it('prevents native Escape dismissal while pending and closes before cancelling when ready', (): void => {
    const { dialog, cancelEvent } = dialogFixture();
    let pending = true;
    const oncancel = vi.fn((): void => { expect(dialog.open).toBe(false); });
    const cleanup = nativeDialog(oncancel, () => !pending)(dialog);
    const blocked = cancelEvent();
    dialog.dispatchEvent(blocked);
    expect(blocked.defaultPrevented).toBe(true);
    expect(dialog.open).toBe(true);
    expect(dialog.close).not.toHaveBeenCalled();
    expect(oncancel).not.toHaveBeenCalled();
    pending = false;
    const allowed = cancelEvent();
    dialog.dispatchEvent(allowed);
    expect(allowed.defaultPrevented).toBe(true);
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(oncancel).toHaveBeenCalledTimes(1);
    if (typeof cleanup === 'function') cleanup();
    expect(dialog.close).toHaveBeenCalledTimes(1);
  });

  it('closes an open dialog on cleanup and removes the cancel listener', (): void => {
    const { dialog, cancelEvent } = dialogFixture();
    const oncancel = vi.fn();
    const cleanup = nativeDialog(oncancel)(dialog);
    if (typeof cleanup === 'function') cleanup();
    expect(dialog.close).toHaveBeenCalledTimes(1);
    expect(dialog.open).toBe(false);
    const event = cancelEvent();
    dialog.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
    expect(oncancel).not.toHaveBeenCalled();
    expect(dialog.close).toHaveBeenCalledTimes(1);
  });
});
