import {
  CodexPluginArchiveSchema,
  CodexPluginReceiptSchema,
  CodexPluginRequestSchema,
  type CodexPluginDownloader,
  type CodexPluginPackager,
  type CodexPluginReceipt
} from '$lib/codex-plugin/contracts';

type DownloadStatus =
  | { state: 'idle' }
  | { state: 'preparing' }
  | { state: 'downloaded'; receipt: CodexPluginReceipt }
  | { state: 'failed'; message: string };

export class CodexPluginState {
  #status = $state<DownloadStatus>({ state: 'idle' });
  #disposed = false;

  constructor(
    private readonly endpoint: () => string,
    private readonly packager: CodexPluginPackager,
    private readonly downloader: CodexPluginDownloader
  ) {}

  get pending(): boolean {
    return this.#status.state === 'preparing';
  }

  get error(): string {
    return this.#status.state === 'failed' ? this.#status.message : '';
  }

  get installation(): { filename: string; command: string } | null {
    if (this.#status.state !== 'downloaded') return null;
    const current = CodexPluginRequestSchema.safeParse({ endpoint: this.endpoint() });
    const receipt = this.#status.receipt;
    if (!current.success || current.data.endpoint !== receipt.endpoint) return null;
    return {
      filename: receipt.filename,
      command: 'codex plugin marketplace add .'
    };
  }

  download = async (): Promise<void> => {
    if (this.#disposed || this.pending) return;
    this.#status = { state: 'preparing' };
    try {
      const request = CodexPluginRequestSchema.parse({ endpoint: this.endpoint() });
      const archive = CodexPluginArchiveSchema.parse(await this.packager.prepare(request));
      if (this.#disposed) return;
      const current = CodexPluginRequestSchema.safeParse({ endpoint: this.endpoint() });
      if (!current.success || current.data.endpoint !== request.endpoint) {
        this.#status = { state: 'idle' };
        return;
      }
      if (archive.endpoint !== request.endpoint) throw new Error('Package endpoint mismatch');
      this.downloader.save(archive);
      this.#status = { state: 'downloaded', receipt: CodexPluginReceiptSchema.parse(archive) };
    } catch {
      if (!this.#disposed) {
        this.#status = {
          state: 'failed',
          message: 'Could not download the Codex plugin. Check that the MCP URL uses HTTPS (or loopback HTTP), contains no credentials or query parameters, and try again.'
        };
      }
    }
  };

  dispose = (): void => {
    this.#disposed = true;
  };
}
