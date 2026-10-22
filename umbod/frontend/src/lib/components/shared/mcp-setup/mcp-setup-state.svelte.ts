import type { ClipboardWriter } from '$lib/admin/clipboard';
import type { ToastApi } from '$lib/components/feedback/toast-state.svelte';

export const setupPrompt = 'Set up Umbod for my agent across projects. Read the Umbod MCP resource umbod://setup/agent-instructions and follow its instructions to add Umbod discovery guidance to my user-scoped agent instructions, preserving existing content. Verify discovery without executing app tools and report which file changed. If you cannot access the resource or connection, explain the problem instead of claiming setup succeeded.';

export class McpSetupState {
  copied = $state(false);

  constructor(
    private readonly endpoint: () => string,
    private readonly clipboard: ClipboardWriter,
    private readonly toast: ToastApi
  ) {}

  get copilotConfiguration(): string {
    return JSON.stringify({
      servers: { umbod: { type: 'http', url: this.endpoint() } }
    }, null, 2);
  }

  copySetupPrompt = async (): Promise<void> => {
    try {
      await this.clipboard.writeText(setupPrompt);
      this.copied = true;
      this.toast.success('Setup prompt copied to clipboard');
    } catch {
      this.copied = false;
      this.toast.error('Could not copy setup prompt');
    }
  };
}
