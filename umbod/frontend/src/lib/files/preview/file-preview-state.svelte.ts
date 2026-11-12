import type { PreviewConfigurationProvider } from './configuration';
import { formatFileSize } from '../state/upload-state.svelte';
import type { NodeSummary } from '../domain/schemas';
import { PreviewReadError } from './ports';
import type { FileContentPort, FilePreviewAdapter, FilePreviewResolver } from './ports';

export type PreviewPhase = 'hidden' | 'unsupported' | 'loading' | 'ready' | 'empty' | 'error' | 'denied' | 'sign-in' | 'missing' | 'too-large';

export class FilePreviewState {
  private currentPhase = $state<PreviewPhase>('hidden');
  private currentContent = $state('');
  private currentAdapter = $state.raw<FilePreviewAdapter | undefined>(undefined);
  private currentMaxBytes = $state<number | undefined>(undefined);
  private node: NodeSummary | undefined;
  private generation = $state(0);
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly contentSource: FileContentPort, private readonly resolver: FilePreviewResolver, private readonly configuration: PreviewConfigurationProvider) {}

  get maxBytes(): number | undefined { return this.currentMaxBytes; }
  get formattedMaxSize(): string {
    const bytes = this.currentMaxBytes;
    if (bytes === undefined) return '';
    return bytes < 1024 || bytes % 1048576 === 0 || (bytes < 1048576 && bytes % 1024 === 0)
      ? formatFileSize(bytes) : `${bytes} bytes`;
  }

  get phase(): PreviewPhase { return this.currentPhase; }
  get content(): string { return this.currentContent; }
  get adapter(): FilePreviewAdapter | undefined { return this.currentAdapter; }

  select = async (node: NodeSummary): Promise<void> => {
    if (this.disposed) return;
    this.reset();
    this.node = node;
    if (node.kind !== 'file' || !node.permissions.can_discover || !node.permissions.can_read) return;
    this.currentAdapter = this.resolver.resolve(node);
    if (!this.currentAdapter) {
      this.currentPhase = 'unsupported';
      return;
    }
    const generation = this.generation;
    this.controller = new AbortController();
    const signal = this.controller.signal;
    this.currentPhase = 'loading';
    try {
      const { filesystemPreviewMaxBytes } = await this.configuration.get();
      if (this.disposed || signal.aborted || generation !== this.generation) return;
      this.currentMaxBytes = filesystemPreviewMaxBytes;
      const content = await this.currentAdapter.read(this.contentSource, node.id, signal);
      if (this.disposed || signal.aborted || generation !== this.generation) return;
      this.currentContent = content;
      this.currentPhase = content.trim().length === 0 ? 'empty' : 'ready';
    } catch (error) {
      if (this.disposed || signal.aborted || generation !== this.generation) return;
      this.currentContent = '';
      this.currentPhase = error instanceof PreviewReadError ? error.reason : 'error';
    }
  };

  createRenderErrorHandler = (): (() => void) => {
    const generation = this.generation;
    return (): void => {
      if (this.disposed || generation !== this.generation || this.currentPhase !== 'ready') return;
      this.currentContent = '';
      this.currentPhase = 'error';
    };
  };

  retry = async (): Promise<void> => {
    if (this.node && this.currentPhase !== 'loading') await this.select(this.node);
  };

  reset = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.controller = undefined;
    this.node = undefined;
    this.currentContent = '';
    this.currentMaxBytes = undefined;
    this.currentAdapter = undefined;
    this.currentPhase = 'hidden';
  };

  dispose = (): void => {
    this.reset();
    this.disposed = true;
  };
}
