import type { NodeSummary } from '$lib/files/domain/schemas';
import { PreviewReadError, type FileContentPort, type FilePreviewAdapter } from '$lib/files/preview/ports';
import ImagePreview from './ImagePreview.svelte';
import { detectRasterMime, supportsRasterImage } from './image-format';

export const imagePreviewAdapter: FilePreviewAdapter = {
  component: ImagePreview,
  supports(file: NodeSummary): boolean {
    const contentType = typeof file.metadata.content_type === 'string' ? file.metadata.content_type : '';
    return supportsRasterImage(file.name, contentType);
  },
  async read(source: FileContentPort, id: string, signal: AbortSignal): Promise<string> {
    const bytes = await source.readBytes(id, signal);
    if (bytes.length === 0) return '';
    const mime = detectRasterMime(bytes);
    if (!mime) throw new PreviewReadError('error');
    let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return 'data:' + mime + ';base64,' + btoa(binary);
  }
};
