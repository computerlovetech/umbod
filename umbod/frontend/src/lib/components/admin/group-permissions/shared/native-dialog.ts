import type { Attachment } from 'svelte/attachments';

export function nativeDialog(oncancel: () => void, canCancel: () => boolean = () => true): Attachment<HTMLDialogElement> {
  return (dialog: HTMLDialogElement): (() => void) => {
    const cancel = (event: Event): void => {
      event.preventDefault();
      if (!canCancel()) return;
      dialog.close();
      oncancel();
    };
    dialog.addEventListener('cancel', cancel);
    dialog.showModal();
    dialog.querySelector<HTMLButtonElement>('[data-dialog-cancel]')?.focus();
    return (): void => {
      dialog.removeEventListener('cancel', cancel);
      if (dialog.open) dialog.close();
    };
  };
}
