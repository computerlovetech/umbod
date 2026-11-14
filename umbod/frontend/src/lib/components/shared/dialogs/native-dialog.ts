import type { Attachment } from 'svelte/attachments';

export function focusDialogControl(dialog: HTMLDialogElement, initialFocus: string = '[data-dialog-cancel]'): void {
  const requested = dialog.querySelector<HTMLElement>(initialFocus);
  const close = dialog.querySelector<HTMLButtonElement>('button[data-dialog-close]:not(:disabled)');
  const buttons = Array.from(dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'));
  const action = buttons.find((button: HTMLButtonElement): boolean => !button.closest('header'));
  const target = requested ?? close ?? action ?? buttons[0];
  target?.focus({ preventScroll: true });
}

export function nativeDialog(oncancel: () => void, canCancel: () => boolean = () => true, initialFocus: string = '[data-dialog-cancel]'): Attachment<HTMLDialogElement> {
  return (dialog: HTMLDialogElement): (() => void) => {
    const cancel = (event: Event): void => {
      event.preventDefault();
      if (!canCancel()) return;
      dialog.close();
      oncancel();
    };
    dialog.addEventListener('cancel', cancel);
    dialog.showModal();
    focusDialogControl(dialog, initialFocus);
    return (): void => {
      dialog.removeEventListener('cancel', cancel);
      if (dialog.open) dialog.close();
    };
  };
}
