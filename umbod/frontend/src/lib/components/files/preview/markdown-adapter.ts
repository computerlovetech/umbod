import type { NodeSummary } from '$lib/files/domain/schemas';
import type { FileContentPort, FilePreviewAdapter } from '$lib/files/preview/ports';
import MarkdownPreview from './MarkdownPreview.svelte';

export const markdownPreviewAdapter: FilePreviewAdapter = {
  component: MarkdownPreview,
  read(source: FileContentPort, id: string, signal: AbortSignal): Promise<string> {
    return source.readText(id, signal);
  },
  supports(file: NodeSummary): boolean {
    const mime = typeof file.metadata.content_type === 'string' ? file.metadata.content_type.split(';')[0].trim().toLowerCase() : '';
    if (mime === 'text/markdown' || mime === 'text/x-markdown') return true;
    if (mime && mime !== 'text/plain' && mime !== 'application/octet-stream') return false;
    return /\.(md|markdown)$/i.test(file.name);
  }
};
