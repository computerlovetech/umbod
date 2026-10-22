import type { Attachment } from 'svelte/attachments';

export function modalDialog(close: () => void, fallbackId: string): Attachment<HTMLDialogElement> {
  return (dialog: HTMLDialogElement): (() => void) => {
    const document = dialog.ownerDocument;
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const cancel = (event: Event): void => {
      event.preventDefault();
      close();
    };
    dialog.addEventListener('cancel', cancel);
    dialog.showModal();
    dialog.querySelector<HTMLElement>('[data-dialog-title]')?.focus();
    return (): void => {
      dialog.removeEventListener('cancel', cancel);
      if (dialog.open) dialog.close();
      queueMicrotask((): void => {
        const target = opener?.isConnected && !opener.matches(':disabled') && !opener.closest('[inert]') ? opener : document.getElementById(fallbackId);
        target?.focus();
      });
    };
  };
}
