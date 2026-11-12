import type { Component } from 'svelte';
import type { NodeSummary } from '../domain/schemas';

export type PreviewReadFailure = 'denied' | 'sign-in' | 'missing' | 'too-large' | 'error';

export class PreviewReadError extends Error {
  constructor(readonly reason: PreviewReadFailure) {
    super('File preview read failed: ' + reason);
    this.name = 'PreviewReadError';
  }
}

export interface FileContentPort {
  readText(id: string, signal: AbortSignal): Promise<string>;
  readBytes(id: string, signal: AbortSignal): Promise<Uint8Array>;
}

export interface PreviewProps {
  content: string;
  onError?: () => void;
}

export interface FilePreviewAdapter {
  readonly component: Component<PreviewProps>;
  supports(file: NodeSummary): boolean;
  read(source: FileContentPort, id: string, signal: AbortSignal): Promise<string>;
}

export interface FilePreviewResolver {
  resolve(file: NodeSummary): FilePreviewAdapter | undefined;
}

export class PreviewRegistry implements FilePreviewResolver {
  constructor(private readonly adapters: readonly FilePreviewAdapter[]) {}

  resolve(file: NodeSummary): FilePreviewAdapter | undefined {
    return this.adapters.find((adapter: FilePreviewAdapter): boolean => adapter.supports(file));
  }
}
