import type { Attachment } from 'svelte/attachments';
import { focusDialogControl } from '$lib/components/shared/dialogs/native-dialog';

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
    focusDialogControl(dialog);
    return (): void => {
      dialog.removeEventListener('cancel', cancel);
      if (dialog.open) dialog.close();
      queueMicrotask((): void => {
        if (document.activeElement?.closest('dialog[open]')) return;
        const target = opener?.isConnected && !opener.matches(':disabled') && !opener.closest('[inert]') ? opener : document.getElementById(fallbackId);
        target?.focus();
      });
    };
  };
}
