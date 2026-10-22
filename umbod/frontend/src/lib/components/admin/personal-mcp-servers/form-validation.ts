import type { Attachment } from 'svelte/attachments';

export function captureInvalidSubmission(onInvalid: () => void): Attachment<HTMLFormElement> {
  return (form: HTMLFormElement): (() => void) => {
    const handleInvalid = (): void => {
      onInvalid();
      const secret = form.querySelector<HTMLInputElement>('input[name="clientSecret"]');
      if (secret) secret.value = '';
    };
    form.addEventListener('invalid', handleInvalid, true);
    return (): void => form.removeEventListener('invalid', handleInvalid, true);
  };
}
