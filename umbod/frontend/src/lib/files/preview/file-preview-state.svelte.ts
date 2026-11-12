import type { NodeSummary } from '../domain/schemas';
import { PreviewReadError } from './ports';
import type { FileContentPort, FilePreviewAdapter, FilePreviewResolver } from './ports';

export type PreviewPhase = 'hidden' | 'unsupported' | 'loading' | 'ready' | 'empty' | 'error' | 'denied' | 'sign-in' | 'missing' | 'too-large';

export class FilePreviewState {
  private currentPhase = $state<PreviewPhase>('hidden');
  private currentContent = $state('');
  private currentAdapter = $state.raw<FilePreviewAdapter | undefined>(undefined);
  private node: NodeSummary | undefined;
  private generation = 0;
  private controller: AbortController | undefined;
  private disposed = false;

  constructor(private readonly contentSource: FileContentPort, private readonly resolver: FilePreviewResolver) {}

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

  retry = async (): Promise<void> => {
    if (this.node && this.currentPhase !== 'loading') await this.select(this.node);
  };

  reset = (): void => {
    ++this.generation;
    this.controller?.abort();
    this.controller = undefined;
    this.node = undefined;
    this.currentContent = '';
    this.currentAdapter = undefined;
    this.currentPhase = 'hidden';
  };

  dispose = (): void => {
    this.reset();
    this.disposed = true;
  };
}
