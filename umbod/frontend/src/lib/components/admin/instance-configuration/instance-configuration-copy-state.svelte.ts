import type { ClipboardWriter } from "$lib/admin/clipboard";
import type { InstanceConfigurationEntry } from "$lib/admin/instance-configuration";
import type { ToastApi } from "$lib/components/feedback/toast-state.svelte";

export function formatConfigurationValue(entry: InstanceConfigurationEntry): string {
  if (entry.type === "string_list") {
    return entry.value.join(", ");
  }
  return String(entry.value);
}

export class InstanceConfigurationCopyState {
  copiedTarget = $state<string | null>(null);
  private copiedValue = $state<string | null>(null);
  copyFailed = $state(false);

  constructor(
    private readonly clipboard: ClipboardWriter,
    private readonly toast: ToastApi
  ) {}

  isCopied = (entry: InstanceConfigurationEntry): boolean => {
    return this.copiedTarget === entry.variable && this.copiedValue === formatConfigurationValue(entry);
  };

  copyEntry = async (entry: InstanceConfigurationEntry): Promise<void> => {
    await this.copy(entry.variable, formatConfigurationValue(entry));
  };

  private copy = async (target: string, value: string): Promise<void> => {
    try {
      await this.clipboard.writeText(value);
      this.copiedTarget = target;
      this.copiedValue = value;
      this.copyFailed = false;
      this.toast.success("Value copied.");
    } catch {
      this.copiedTarget = null;
      this.copiedValue = null;
      this.copyFailed = true;
      this.toast.error("Could not copy to the clipboard.");
    }
  };
}
