import { expect, test } from 'vitest';
import { filesystemNode } from '$lib/files/fixtures.test-support';
import { InMemoryFileContent } from '$lib/files/preview/in-memory-content.test-support';
import { pdfPreviewAdapter } from './pdf-adapter';

test.each<[string, string | undefined, boolean]>([
  ['report', 'application/pdf', true],
  ['report.pdf', 'APPLICATION/PDF; version=1.7', true],
  ['REPORT.PDF', undefined, true],
  ['report.pdf', 'application/octet-stream', true],
  ['report.pdf', 'text/html', false],
  ['report.pdf', 'text/plain', false],
  ['notes.md', undefined, false]
])('selects %s with MIME %s as PDF: %s', (name: string, mime: string | undefined, supported: boolean): void => {
  const file = filesystemNode({ name, kind: 'file', metadata: { content_type: mime ?? {}, attributes: {} } });
  expect(pdfPreviewAdapter.supports(file)).toBe(supported);
});

test('preserves non-UTF8 PDF bytes in a fixed PDF data URL', async (): Promise<void> => {
  const bytes = new Uint8Array([37, 80, 68, 70, 45, 49, 46, 55, 10, 255, 0, 128]);
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => bytes);
  const signal = new AbortController().signal;
  const content = await pdfPreviewAdapter.read(source, 'file', signal);
  expect(content).toBe('data:application/pdf;base64,' + btoa(String.fromCharCode(...bytes)));
  expect(source.requests).toEqual([{ id: 'file', signal }]);
});

test('keeps empty PDFs empty for the preview container', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<Uint8Array> => new Uint8Array());
  expect(await pdfPreviewAdapter.read(source, 'file', new AbortController().signal)).toBe('');
});

test('rejects non-PDF content instead of embedding arbitrary documents', async (): Promise<void> => {
  const source = new InMemoryFileContent(async (): Promise<string> => '<script>alert(1)</script>');
  await expect(pdfPreviewAdapter.read(source, 'file', new AbortController().signal)).rejects.toMatchObject({ reason: 'error' });
});
