import type { NodeSummary } from '$lib/files/domain/schemas';
import { PreviewReadError, type FileContentPort, type FilePreviewAdapter } from '$lib/files/preview/ports';
import PdfPreview from './PdfPreview.svelte';

export const pdfPreviewAdapter: FilePreviewAdapter = {
  component: PdfPreview,
  supports(file: NodeSummary): boolean {
    const mime = typeof file.metadata.content_type === 'string' ? file.metadata.content_type.split(';')[0].trim().toLowerCase() : '';
    if (mime === 'application/pdf') return true;
    if (mime && mime !== 'application/octet-stream') return false;
    return /\.pdf$/i.test(file.name);
  },
  async read(source: FileContentPort, id: string, signal: AbortSignal): Promise<string> {
    const bytes = await source.readBytes(id, signal);
    if (bytes.length === 0) return '';
    if (new TextDecoder().decode(bytes.subarray(0, 5)) !== '%PDF-') throw new PreviewReadError('error');
    let binary = '';
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return 'data:application/pdf;base64,' + btoa(binary);
  }
};
