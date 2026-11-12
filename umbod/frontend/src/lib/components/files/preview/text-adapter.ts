import type { NodeSummary } from '$lib/files/domain/schemas';
import type { FileContentPort, FilePreviewAdapter } from '$lib/files/preview/ports';
import TextPreview from './TextPreview.svelte';

export const textPreviewAdapter: FilePreviewAdapter = {
  component: TextPreview,
  read(source: FileContentPort, id: string, signal: AbortSignal): Promise<string> {
    return source.readText(id, signal);
  },
  supports(file: NodeSummary): boolean {
    const mime = typeof file.metadata.content_type === 'string' ? file.metadata.content_type.split(';')[0].trim().toLowerCase() : '';
    if (['text/plain', 'application/yaml', 'application/x-yaml', 'text/yaml', 'text/x-yaml', 'application/toml', 'application/x-toml', 'text/toml', 'text/x-toml', 'text/x-log'].includes(mime)) return true;
    if (mime && mime !== 'application/octet-stream') return false;
    return /\.(txt|yaml|yml|toml|log)$/i.test(file.name);
  }
};
