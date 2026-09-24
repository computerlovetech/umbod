import type { ClipboardWriter } from '$lib/admin/clipboard';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';

export type CopyFeedback = 'idle' | 'copied' | 'failed';

export class CopyableValueState {
  feedback = $state<CopyFeedback>('idle');

  constructor(
    readonly value: string,
    private readonly clipboard: ClipboardWriter,
    private readonly toast: ToastApi
  ) {}

  copy = async (): Promise<void> => {
    try {
      await this.clipboard.writeText(this.value);
      this.feedback = 'copied';
      this.toast.success('URI copied to clipboard');
    } catch {
      this.feedback = 'failed';
      this.toast.error('Could not copy URI');
    }
  };
}
